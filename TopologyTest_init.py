from TopologyTest import TopologyTest

# Define paths to GeoJSON files and configuration
roads_geojson = r'C:\Python\TopologyTest\test_data\roads.geojson'
buildings_geojson = r'C:\Python\TopologyTest\test_data\buildings.geojson'  # Use the fixed GeoJSON
rules_file = r'C:\Python\TopologyTest\attributes.json'
config_file = r'C:\Python\TopologyTest\config.json'  # Ensure this file exists

# Create TopologyTest for roads from a GeoJSON file
road_checker = TopologyTest(
    geojson_file=roads_geojson,
    dataset_type='roads',
    rules_file=rules_file,
    config_file=config_file
)
print(road_checker.report_summary())

# Generate and save invalid intersections for roads
road_invalid_report = road_checker.report_invalid_intersections()
print(road_invalid_report)

# Create TopologyTest for buildings from the GeoJSON file
building_checker = TopologyTest(
    geojson_file=buildings_geojson,  # Use fixed GeoJSON
    dataset_type='buildings',
    rules_file=rules_file,
    config_file=config_file
)
print(building_checker.report_summary())

# Generate and save invalid intersections for buildings
building_invalid_report = building_checker.report_invalid_intersections()
print(building_invalid_report)
