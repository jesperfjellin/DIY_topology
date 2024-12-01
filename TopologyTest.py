import geojson
import os
import json
from shapely.geometry import shape, mapping, GeometryCollection, MultiLineString, MultiPolygon
from itertools import combinations
import geopandas as gpd

class TopologyTest:
    def __init__(self, geojson_file, dataset_type, rules_file, config_file=None):
        """
        Initialize the TopologyTest with a GeoJSON file, dataset type, rules file, and optional config file.
        :param geojson_file: Path to the GeoJSON file.
        :param dataset_type: The type of dataset, e.g., 'roads' or 'buildings'.
        :param rules_file: Path to the JSON file containing legal intersection rules.
        :param config_file: Path to the JSON file containing configuration parameters.
        """
        self.geojson_file = geojson_file
        self.dataset_type = dataset_type
        self.rules = self._load_rules(rules_file)
        self.config = self._load_config(config_file)
        self.geometries = self._load_geometries(geojson_file)
        self.invalid_intersections = None  # Cache for invalid intersections

    def _load_config(self, config_file):
        """
        Load configuration parameters from a JSON file.
        :param config_file: Path to the JSON file.
        :return: A dictionary containing configuration parameters.
        """
        if config_file and os.path.exists(config_file):
            with open(config_file) as f:
                config = json.load(f)
            return config
        else:
            # default configurations
            return {
                "id_attribute": "id",
                "output_folder_name": "TopologyTest_Output",
                "min_intersection_area": 0  # Set to 0 for roads (intersections have area 0)
            }

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

    def _load_rules(self, rules_file):
        """
        Load legal intersection rules from a JSON file.
        :param rules_file: Path to the JSON file.
        :return: A dictionary containing rules.
        """
        if not os.path.exists(rules_file):
            raise FileNotFoundError(f"Rules file not found: {rules_file}")

        with open(rules_file) as f:
            rules = json.load(f)

        if self.dataset_type not in rules:
            raise ValueError(f"Dataset type '{self.dataset_type}' not found in rules.")

        return rules[self.dataset_type]

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

    def save_invalid_intersections(self, invalid_intersections):
        """
        Save the invalid intersections to a new GeoJSON file in a nested output folder.
        The output filename includes the dataset type to prevent overwriting.
        Each feature includes the two intersecting geometries.
        :param invalid_intersections: List of invalid intersection tuples.
        :return: Path to the output GeoJSON file.
        """
        # Create the output folder
        base_path = os.path.dirname(self.geojson_file)
        output_folder = os.path.join(base_path, self.config.get("output_folder_name", "TopologyTest_Output"))
        os.makedirs(output_folder, exist_ok=True)

        # Prepare GeoJSON features for the invalid intersections
        features = []
        for geom1, geom2, inter_geom, attr1, attr2 in invalid_intersections:
            # For roads (LineStrings), create a MultiLineString of the two lines
            if geom1.geom_type == 'LineString' and geom2.geom_type == 'LineString':
                combined_geom = MultiLineString([geom1, geom2])
            # For polygons (buildings), create a MultiPolygon of the two polygons
            elif geom1.geom_type == 'Polygon' and geom2.geom_type == 'Polygon':
                combined_geom = MultiPolygon([geom1, geom2])
            else:
                # If geometries are of mixed types, create a GeometryCollection
                combined_geom = GeometryCollection([geom1, geom2])

            # Add the combined geometry with references to the original features
            features.append({
                "type": "Feature",
                "geometry": mapping(combined_geom),
                "properties": {
                    "status": "invalid_intersection",
                    "feature1_id": attr1.get(self.config.get("id_attribute", "id"), 'N/A'),
                    "feature2_id": attr2.get(self.config.get("id_attribute", "id"), 'N/A')
                }
            })

        # Create the output GeoJSON file with dataset_type in the filename
        output_geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        output_filename = f"invalid_intersections_{self.dataset_type}.geojson"
        output_file = os.path.join(output_folder, output_filename)
        with open(output_file, 'w') as f:
            geojson.dump(output_geojson, f, indent=2)


        return output_file

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

    def report_summary(self):
        """
        Generate a summary report of intersection checks.
        :return: A summary report string.
        """
        invalid_intersections = self.check_intersections()

        total_geometries = len(self.geometries)
        # Collect unique geometry IDs that have at least one invalid intersection
        intersected_ids = set()
        for *_, attr1, attr2 in invalid_intersections:
            id1 = attr1.get(self.config.get("id_attribute", "id"), 'N/A')
            id2 = attr2.get(self.config.get("id_attribute", "id"), 'N/A')
            intersected_ids.add(id1)
            intersected_ids.add(id2)

        num_intersected_geometries = len(intersected_ids)

        # Calculate average invalid intersections per intersected geometry
        average_intersections = len(invalid_intersections) / num_intersected_geometries if num_intersected_geometries else 0

        report = f"Intersection Summary for dataset: {self.dataset_type}\n"
        report += f"Total geometries: {total_geometries}\n"
        report += f"Geometries intersected: {num_intersected_geometries}\n"
        report += f"Average intersections per geometry: {average_intersections:.2f}\n"
        report += f"Percentage intersected: {(num_intersected_geometries / total_geometries) * 100:.2f}%"
        return report
