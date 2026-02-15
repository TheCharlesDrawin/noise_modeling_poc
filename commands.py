from pathlib import Path

import consts



class Command:
    command_sub_path: str
    may_stuck: bool = False

    def get_command_path(self) -> str:
        return str((Path(consts.WPS_SCRIPTS_PATH) / self.command_sub_path).absolute())

    def get_command(self):
        raise NotImplementedError("Subclasses should implement this method.")


class ClearDb(Command):
    command_sub_path = r'Database_Manager/Clean_Database.groovy'

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-areYouSure', 'true',
            ]
        
        return full_command


class ImportOsm(Command):
    command_sub_path = r'Import_and_Export/Import_OSM.groovy'
    def __init__(self, osm_file: Path, srid: int = 3857):
        self.osm_file = osm_file
        self.srid = srid

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-pathFile', str(self.osm_file.absolute()),
            '-targetSRID', str(self.srid),
            ]
        
        return full_command
    
class ImportFile(Command):
    command_sub_path = r'Import_and_Export/Import_File.groovy'
    def __init__(self, osm_file: Path, srid: int, table_name: str):
        self.osm_file = osm_file
        self.srid = srid
        self.table_name = table_name

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-pathFile', str(self.osm_file.absolute()),
            '-inputSRID', str(self.srid),
            '-tableName', self.table_name,
            ]
        
        return full_command
    

class ImportAscFile(Command):
    command_sub_path = r'Import_and_Export/Import_Asc_File.groovy'
    def __init__(self, tiff_file: Path, srid: int):
        self.tiff_file = tiff_file
        self.srid = srid

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-pathFile', str(self.tiff_file.absolute()),
            '-inputSRID', str(self.srid),
            ]
        
        return full_command
    

class ExportTable(Command):
    command_sub_path = r'Import_and_Export/Export_Table.groovy'
    def __init__(self, export_path: Path, table_name: str):
        self.export_path = export_path
        self.table_name = table_name

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-exportPath', str(self.export_path.absolute()),
            '-tableToExport', self.table_name,
            ]
        
        return full_command


class DropTable(Command):
    command_sub_path = r'Import_and_Export/Drop_a_Table.groovy'
    def __init__(self, table_name: str):
        self.table_name = table_name

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-tableToDrop', self.table_name,
            ]
        
        return full_command


class DelaunayReceivers(Command):
    command_sub_path = r'Receivers/Delaunay_Grid.groovy'

    def __init__(self, building_table_name: str, source_table_name: str, max_area: float, height: float):
        self.building_table_name = building_table_name
        self.source_table_name = source_table_name
        self.max_area = max_area
        self.height = height

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-tableBuilding', self.building_table_name,
            '-sourcesTableName', self.source_table_name,
            '-maxArea', str(self.max_area),
            '-height', str(self.height),
            ]
        
        return full_command
    

class RandomReceivers(Command):
    command_sub_path = r'Receivers/Random_Grid.groovy'

    def __init__(self, building_table_name: str, source_table_name: str, nReceivers: int, height: float, fenceTableName: str):
        self.building_table_name = building_table_name
        self.source_table_name = source_table_name
        self.nReceivers = nReceivers
        self.height = height
        self.fenceTableName = fenceTableName

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-buildingTableName', self.building_table_name,
            '-sourcesTableName', self.source_table_name,
            '-nReceivers', str(self.nReceivers),
            '-height', str(self.height),
            '-fenceTableName', self.fenceTableName,
            ]
        
        return full_command
    

class BuildingsReceivers(Command):
    command_sub_path = r'Receivers/Building_Grid.groovy'

    def __init__(self, building_table_name: str, source_table_name: str, delta: float, height: float, fenceTableName: str):
        self.building_table_name = building_table_name
        self.source_table_name = source_table_name
        self.delta = delta
        self.height = height
        self.fenceTableName = fenceTableName

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-tableBuilding', self.building_table_name,
            '-sourcesTableName', self.source_table_name,
            '-delta', str(self.delta),
            '-height', str(self.height),
            '-fenceTableName', self.fenceTableName,
            ]
        
        return full_command
    

class NoiseLevelFromSource(Command):
    command_sub_path = r'NoiseModelling/Noise_level_from_source.groovy'
    may_stuck = True

    def __init__(
            self,
            building_table_name: str,
            ground_table_name: str,
            source_table_name: str,
            table_receivers: str,
            vertical_diffraction: bool,
            horizontal_diffraction: bool,
            order_of_reflections: int,
            max_reflection_distance: int # meters
        ):

        self.building_table_name = building_table_name
        self.ground_table_name = ground_table_name
        self.source_table_name = source_table_name
        self.table_receivers = table_receivers
        self.vertical_diffraction = vertical_diffraction
        self.horizontal_diffraction = horizontal_diffraction
        self.order_of_reflections = order_of_reflections
        self.max_reflection_distance = max_reflection_distance

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-tableBuilding', self.building_table_name,
            '-tableSources', self.source_table_name,
            '-tableGroundAbs', self.ground_table_name,
            '-tableReceivers', str(self.table_receivers),
            '-tableDEM', 'DEM',
            '-confDiffVertical', str(self.vertical_diffraction),
            '-confDiffHorizontal', str(self.horizontal_diffraction),
            '-confMaxSrcDist', str(20000),
            '-confMaxReflDist', str(200),
            '-confHumidity', str(70),
            '-confTemperature', str(30),
            '-confRaysName', "RAYS",
            '-confReflOrder', str(self.order_of_reflections),
            ]
        
        return full_command
    
class CreateIsosurface(Command):
    command_sub_path = r'Acoustic_Tools/Create_Isosurface.groovy'

    def __init__(self, results_table: str, smooth_coefficient: float, iso_levels: str):
        self.results_table = results_table
        self.smooth_coefficient = smooth_coefficient
        self.iso_levels = iso_levels

    def get_command(self):
        command_path = self.get_command_path()

        full_command = [
            consts.WPS_SCRIPTS_RUNNER,
            '-w', './/',
            '-s', command_path,
            '-resultTable', self.results_table,
            '-smoothCoefficient', str(self.smooth_coefficient),
            '-isoClass', self.iso_levels,
            ]
        
        return full_command 
