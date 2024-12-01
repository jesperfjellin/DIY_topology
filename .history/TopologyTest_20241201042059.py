import geojson
import os
import json
from shapely.geometry import GeometryCollection, MultiLineString, MultiPolygon, Point, LineString, mapping
from shapely.ops import unary_union
from itertools import combinations
import geopandas as gpd

class TopologyTest:
    def __init__(self, geojson_file, dataset_type, config_file):
        """
        Initialize the TopologyTest with a GeoJSON file and config file.
        :param geojson_file: Path to the GeoJSON file to validate.
        :param dataset_type: The type of dataset, e.g., 'roads' or 'buildings'.
        :param config_file: Path to the config file containing all settings and rules.
        """
        self.geojson_file = geojson_file
        self.dataset_type = dataset_type
        self.config = self._load_config(config_file)
        self.rules = self._load_rules(config_file)
        self.geometries = self._load_geometries(geojson_file)
        self.invalid_intersections = None

    def _load_config(self, config_file):
        """
        Load configuration parameters from a JSON file.
        :param config_file: Path to the JSON file.
        :return: Dictionary containing configuration parameters.
        """
        if config_file and os.path.exists(config_file):
            with open(config_file) as f:
                full_config = json.load(f)
                
            # Merge global settings with dataset-specific rules
            config = full_config.get('global_settings', {})
            dataset_rules = full_config.get('dataset_rules', {}).get(self.dataset_type, {})
            
            # Combine settings
            config.update(dataset_rules)
            
            return config
        else:
            # Default configurations
            return {
                "id_attribute": "id",
                "output_folder_name": "TopologyTest_Output",
                "enabled_checks": {
                    "intersections": True,
                    "self_intersections": True,
                    "gaps": True,
                    "dangles": True,
                    "overlaps": True,
                    "containment": True
                },
                "tolerances": {
                    "gap": 0.0,
                    "overlap": 0.0
                },
                "allow_intersection_if": [],
                "allow_overlap_if": []
            }
    def _validate_config_structure(self, config):
        """Validate that the config file has the required structure."""
        required_sections = ['global_settings', 'dataset_rules']
        required_global = ['enabled_checks', 'tolerances']
        
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required section '{section}' in config file")
                
        for setting in required_global:
            if setting not in config['global_settings']:
                raise ValueError(f"Missing required global setting '{setting}'")
                
        if self.dataset_type not in config['dataset_rules']:
            raise ValueError(f"Dataset type '{self.dataset_type}' not found in config")

    def _load_geometries(self, geojson_file):
        """
        Load geometries and attributes from a GeoJSON file.
        :param geojson_file: Path to the GeoJSON file.
        :return: A list of tuples, each containing a shapely geometry and its attributes.
        """
        # Load the GeoJSON using geopandas
        gdf = gpd.read_file(geojson_file)

        # Ensure CRS is WGS84
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
            print(f"Assigned default CRS EPSG:4326 to {geojson_file}")
        else:
            pass  # Removed duplicate logging

        # Extract geometries and attributes
        geometries = []
        for _, row in gdf.iterrows():
            geom = row['geometry']
            # Adjust based on how attributes are stored
            if 'properties' in row and isinstance(row['properties'], dict):
                attributes = row['properties']
            else:
                attributes = row.to_dict()
            geometries.append((geom, attributes))

        return geometries

    def _load_rules(self, config_file):
        """
        Load rules from the config file.
        :param config_file: Path to the config file.
        :return: A dictionary containing rules for the dataset type.
        """
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        with open(config_file) as f:
            config = json.load(f)

        dataset_rules = config.get('dataset_rules', {}).get(self.dataset_type)
        if not dataset_rules:
            raise ValueError(f"Dataset type '{self.dataset_type}' not found in config.")

        return dataset_rules

    def check_intersections(self):
        """
        Check for invalid intersections based on the dataset type and rules.
        :return: A list of invalid intersection tuples containing:
                 (geometry1, geometry2, intersection_geometry, attributes1, attributes2)
        """
        if self.invalid_intersections is not None:
            return self.invalid_intersections  # Return cached results

        invalid_intersections = []
        gdf = gpd.GeoDataFrame(self.geometries, columns=['geometry', 'attributes'])
        sindex = gdf.sindex  # Spatial index

        for idx, row in gdf.iterrows():
            possible_matches_index = list(sindex.intersection(row['geometry'].bounds))
            possible_matches = gdf.iloc[possible_matches_index]

            for _, match in possible_matches.iterrows():
                if idx >= match.name:
                    continue  # Avoid duplicate checks and self-comparison

                if row['geometry'].intersects(match['geometry']):
                    if not self._is_valid_intersection(row['attributes'], match['attributes']):
                        try:
                            inter_geom = row['geometry'].intersection(match['geometry'])
                            # Check if the intersection geometry is valid
                            if not inter_geom.is_valid:
                                continue
                            if inter_geom.area >= self.config.get("min_intersection_area", 0):
                                invalid_intersections.append((row['geometry'], match['geometry'], inter_geom, row['attributes'], match['attributes']))
                        except Exception as e:
                            continue

        self.invalid_intersections = invalid_intersections  # Cache the results
        return invalid_intersections

    def _is_valid_intersection(self, attr1, attr2):
        """
        Check if the intersection between two features is valid based on rules.
        :param attr1: Attributes of the first feature.
        :param attr2: Attributes of the second feature.
        :return: True if the intersection is valid, False otherwise.
        """
        conditions = self.rules.get("allow_intersection_if", [])

        # If no conditions are specified, no intersections are allowed
        if not conditions:
            return False

        # Check each condition; if any condition is met, the intersection is valid
        for condition in conditions:
            attribute = condition.get("attribute")
            allowed_values = condition.get("values", [])

            # Check if either feature meets the condition
            if attr1.get(attribute) in allowed_values or attr2.get(attribute) in allowed_values:
                return True

        # If no conditions are met, the intersection is invalid
        return False

    def save_topology_results(self, results):
        """Save all topology check results to GeoJSON files."""
        output_files = {}
        
        for check_type, issues in results.items():
            if issues and len(issues) > 0:
                output_file = self._save_issues_to_geojson(check_type, issues)
                output_files[check_type] = output_file
        
        return output_files

    def report_invalid_intersections(self):
        """
        Generate a report of invalid intersections and save them to a new GeoJSON file.
        :return: A report string.
        """
        invalid_intersections = self.check_intersections()

        if not invalid_intersections:
            return f"No invalid intersections found in dataset: {self.dataset_type}."

        # Save the invalid intersections to a new GeoJSON file
        output_file = self.save_invalid_intersections(invalid_intersections)

        # Generate a report
        report = f"Invalid intersections found in dataset: {self.dataset_type}\n"
        report += f"Number of invalid intersections: {len(invalid_intersections)}\n"
        report += f"Invalid intersections have been saved to: {output_file}\n"
        return report
    
    def check_self_intersections(self):
        '''Check if any individual geometry intersects with itself.'''
        self_intersections = []
        for geom, attrs in self.geometries:
            if not geom.is_simple:
                self_intersections.append((geom, attrs))
        return self_intersections

    def check_gaps(self, tolerance=0.0):
        """
        Check for gaps between adjacent polygons.
        :param tolerance: Maximum allowed gap width
        """
        if not self.geometries:
            return []
        
        # Create a union of all polygons
        all_polys = unary_union([geom for geom, _ in self.geometries])
        # Create a slightly larger boundary
        buffered = all_polys.buffer(tolerance)
        # Find gaps
        gaps = buffered.difference(all_polys)
        return gaps if not gaps.is_empty else []
    
    def check_dangles(self):
        """Check for dangling ends in line networks."""
        dangles = []
        # Create network from all lines
        network = unary_union([geom for geom, _ in self.geometries])
        
        for geom, attrs in self.geometries:
            if geom.geom_type == 'LineString':
                start_point = Point(geom.coords[0])
                end_point = Point(geom.coords[-1])
                # Check if endpoints connect to other lines
                if not network.difference(geom).intersects(start_point) or \
                not network.difference(geom).intersects(end_point):
                    dangles.append((geom, attrs))
        return dangles
    
    def check_overlaps(self, tolerance=0.0):
        """
        Check for overlapping geometries beyond simple intersection points.
        :param tolerance: Minimum overlap area to consider
        """
        overlaps = []
        gdf = gpd.GeoDataFrame(self.geometries, columns=['geometry', 'attributes'])
        
        for idx1, row1 in gdf.iterrows():
            for idx2, row2 in gdf.iloc[idx1+1:].iterrows():
                if row1['geometry'].overlaps(row2['geometry']):
                    overlap_area = row1['geometry'].intersection(row2['geometry']).area
                    if overlap_area > tolerance:
                        overlaps.append((row1['geometry'], row2['geometry'], 
                                    row1['attributes'], row2['attributes']))
        return overlaps
    
    def check_containment(self):
        """Check for geometries completely contained within others."""
        containment_issues = []
        gdf = gpd.GeoDataFrame(self.geometries, columns=['geometry', 'attributes'])
        
        for idx1, row1 in gdf.iterrows():
            for idx2, row2 in gdf.iloc[idx1+1:].iterrows():
                if row1['geometry'].contains(row2['geometry']):
                    containment_issues.append((row1['geometry'], row2['geometry'],
                                            row1['attributes'], row2['attributes']))
        return containment_issues
    
    def validate_topology(self):
        """Run all enabled topology checks and return comprehensive results."""
        results = {
            'intersections': self.check_intersections() if self.config.get('check_intersections', True) else None,
            'self_intersections': self.check_self_intersections() if self.config.get('check_self_intersections', True) else None,
            'gaps': self.check_gaps() if self.config.get('check_gaps', True) else None,
            'dangles': self.check_dangles() if self.config.get('check_dangles', True) else None,
            'overlaps': self.check_overlaps() if self.config.get('check_overlaps', True) else None,
            'containment': self.check_containment() if self.config.get('check_containment', True) else None
        }
        return results

    def report_summary(self):
        """Generate a comprehensive summary report of all topology checks."""
        results = self.validate_topology()
        
        report = f"Topology Summary for dataset: {self.dataset_type}\n"
        report += f"Total geometries: {len(self.geometries)}\n\n"
        
        for check_type, issues in results.items():
            if issues is not None:
                report += f"{check_type.replace('_', ' ').title()}: {len(issues)} issues found\n"
        
        return report