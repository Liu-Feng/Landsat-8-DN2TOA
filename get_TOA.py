# -*- coding:utf-8 -*-
'''
Copyright: LiuFeng
Time: 2019.7.29
Email: liu.feng.9610@gmail.com
'''

import gdal
import numpy as np
import math
import time
import os
import redis

import argparse

from datetime import datetime, timedelta
from numpy import radians, ndarray, sin, cos, degrees, arctan2, arcsin, tan, arccos
import inspect



parser = argparse.ArgumentParser()
parser.add_argument('--host_name', type=str, default="", help='host name used in redis')
parser.add_argument('--port', type=str, default="6379", help='port used in redis')
parser.add_argument('--password', type=str, default="", help="Password of host_name")
parser.add_argument('--band_nums', type=int, default=7, help=" Band numbers of processing")
parser.add_argument('--key_name', type=str, default='TOA_SETS', help=" The set key of waiting do")
parser.add_argument('--success_key', type=str, default='TOA_SUCCESS', help="The set key of success")
parser.add_argument('--fail_key', type=str, default='TOA_FAIL', help="The set key of fail")
parser.add_argument('--block_size', type=int, default=512, help="BLOCKXSIZE and BLOCKYSIZE in options")

FLAGS = parser.parse_args()

host_name = FLAGS.host_name
port = FLAGS.port
password = FLAGS.password
band_nums = FLAGS.band_nums
key_name = FLAGS.key_name
fail_key = FLAGS.fail_key
success_key = FLAGS.success_key
block_size = FLAGS.block_size


def get_band_mtl_filenames(file_dir, band_nums):
    '''
    This code is for analuse the file which contian tif files and mtl file,
    :param dir_name:
    :param band_nums:
    :return: retrun the band files and mtl in dir
    '''

    band_files = []
    if not os.path.isdir(file_dir):
        print('File is null')
        return
    else:
        files_in_dir_name = os.listdir(file_dir)
        files_without_ext = []
        mtl_file = ""
        for file in files_in_dir_name:
            if file.endswith(bytes(".txt", encoding='utf-8')):
                # mtl_file = file
                if file[:-4].endswith(bytes("MTL", encoding='utf-8')):
                    mtl_file = file
            elif file.endswith(bytes(".TIF", encoding='utf-8')):
                files_without_ext.append(file[:27])
            else:
                continue

    for i in range(1, band_nums + 1):
        band_file = bytes(files_without_ext[0].decode() + str(i) + ".TIF", encoding='utf-8')
        band_files.append(band_file)

    return mtl_file, band_files


def DN2TOA(file_dir, band_nums):
    '''
    this code is transfer DN to TOA and write to out_file_dir in .TIF format
    :param in_dir_name:
    :param band_nums: the number
    :param out_file_dir:
    :return: write toa file in .TIF format
    '''

    mtl_file, band_files = get_band_mtl_filenames(file_dir, band_nums)
    mtl_path = os.path.join(file_dir, mtl_file)
    meta = landsat_metadata(mtl_path)
    if not os.path.isdir(os.path.join(file_dir.decode(), "TOA")):
        os.mkdir(os.path.join(file_dir.decode(), "TOA"))

    for band_num in range(1, band_nums + 1):
        band_file = band_files[band_num - 1]

        band_num = str(band_num)

        '''' the files generated in midele process '''
        band_out_dir = os.path.join(os.path.join(file_dir.decode(), "TOA"),
                                    band_file[:-4].decode() + "_REF" + ".TIF")
        in_band_dir = os.path.join(file_dir, band_file)

        proj, trans, band_array = read_single_band_tif(in_band_dir)

        Mp = getattr(meta, "REFLECTANCE_MULT_BAND_{0}".format(band_num))  # multiplicative scaling factor
        Ap = getattr(meta, "REFLECTANCE_ADD_BAND_{0}".format(band_num))  # additive rescaling factor
        SEA = getattr(meta, "SUN_ELEVATION") * (math.pi / 180)  # sun elevation angle theta_se

        null_raster = np.where(band_array != 0, band_array, np.NaN)
        # calculate top-of-atmosphere reflectance
        ''' '''
        TOA_ref = (((null_raster * Mp) + Ap) / (math.sin(SEA))) * 10000
        TOA_ref = TOA_ref.astype(np.uint16)

        write_single_tif(band_out_dir, proj, trans, TOA_ref)


def write_to_redis(file_dir, is_success, password, host_name, success_key, fail_key, port):
    '''
    Write the file_dir to sucess or fail set in redis
    :param file_dir:
    :param is_success:
    :param password:
    :param host_name:
    :param success_key:
    :param fail_key:
    :param port:
    :return:
    '''
    if is_success:
        success_qu = redis.Redis(host=host_name, password=password, port=port)
        success_qu.sadd(success_key, file_dir)
    else:
        fail_qu = redis.Redis(host=host_name, password=password, port=port)
        fail_qu.sadd(fail_key, file_dir)


# def tranfer_cog(file_dir, band_nums):
#     '''
#     tranfer toa file from gtif to specific format, which used cmd line in shell
#     :param file_dir: the file contains DN files
#     :param band_nums:
#     :param log_dir:
#     :return:  if success: the file will be write to file_dir/toa/1....7 and return success
#               else:     if there are
#     '''
#
#     DN2TOA(file_dir, band_nums)
#     _, DN_files = get_band_mtl_filenames(file_dir, band_nums)
#
#     raw_toa_files = os.listdir(os.path.join(file_dir.decode(), "raw_toa"))
#     ''' the file store the specific format toa file'''
#     targeted_toa = os.path.join(file_dir.decode(), "TOA")
#     if not os.path.isdir(targeted_toa):
#         os.mkdir(targeted_toa)
#
#     for i in range(1, len(raw_toa_files) + 1):
#         ''' the file name of band in toa type '''
#         raw_toa_file = raw_toa_files[i - 1]
#         DN_file = DN_files[i - 1]
#
#         DN_file_abs_dir = os.path.join(file_dir, DN_file)
#         in_tif = os.path.join(os.path.join(file_dir.decode(), "raw_toa"), raw_toa_file)
#
#         out_tif = os.path.join(targeted_toa, raw_toa_file)
#
#         '''delete the original DN file'''
#         # os.system("rm -rf {0}".format(DN_file_abs_dir))
#
#         os.system(
#             "gdal_translate {0} {1} -co TILED=YES -co COPY_SRC_OVERVIEWS=YES -co COMPRESS=DEFLATE".format(in_tif,
#                                                                                                           out_tif))
#
#     os.system("rm -rf {0}".format(os.path.join(file_dir.decode(), "raw_toa")))
#
#     ''' the cmd line used in linux or macos to remove a dir snd and files in it '''
#     ''' remove cmd used in windows'''
#     # os.system("rd /s /q {0}".format(os.path.join(file_dir.decode(),"raw_toa")))
#
#     ''' delete the DN files apart from 1-7 '''
#     # redundat_files = ["8", "9", "10", "11", "QA"]
#     # for redundat_file in redundat_files:
#     #     delete_file = os.path.join(file_dir, DN_files[0][:-5]+redundat_file+".TIF")
#     #     os.system("rm -rf {0}".format(delete_file))
#
#     # success_or_not = glob.glob(pathname=targeted_toa+'*.tif') == band_nums
#     # # test_success_or_not(targeted_toa,band_nums, log_dir)
#     #
#     # ''' delete the raw_toa file'''
#     # os.system("rm -rf {0}".format(os.path.join(file_dir,"raw_toa")))
#     # return success_or_not


def read_wait_dirs(host_name, port, password, band_nums, key_name, fail_key, success_key):
    '''
    read dir from redis, and transfer data from DN to TOA
    :param host_name:
    :param port:
    :param password:
    :param band_nums:
    :param key_name:
    :param fail_key:
    :param success_key:
    :return:
    '''

    undo_qu = redis.Redis(host=host_name, port=port, password=password)

    while undo_qu.scard(key_name) > 0:
        start_time = time.time()

        file_dir = undo_qu.spop(key_name)

        try:
            DN2TOA(file_dir, band_nums)

            write_to_redis(file_dir, True, password, host_name, success_key, fail_key, port)
            print(time.time() - start_time)

        except BaseException:

            write_to_redis(file_dir, False, password, host_name, success_key, fail_key, port)
            print(time.time() - start_time)
        continue


# def test_success_or_not(toa_dir,band_nums, log_dir):
#     if glob.glob(pathname=toa_dir + '*.tif') != band_nums:
#         log_out_wrong_dir(log_dir, toa_dir[:-4])
#     # else:
#     #     log_out_wrong_dir(log_dir, toa_dir[:-4])


def log_out_wrong_dir(log_dir, dir_info):
    '''
    write the wrong dir_info in log_dir/fail_dir.txt
    :param log_dir:
    :param dir_info:
    :return:
    '''
    if not os.path.isfile(log_dir):
        print("make a txt file in {0}".format(log_dir + "/fail_dir.txt"))

    with open(os.path.join(log_dir, "fail_dir.txt"), 'w') as fail_dir:
        fail_dir.write(dir_info)
        fail_dir.close()


def read_single_band_tif(band_dir):
    band = gdal.Open(band_dir)
    proj = band.GetProjection()
    trans = band.GetGeoTransform()
    band_array = band.ReadAsArray(0, 0, band.RasterXSize, band.RasterYSize)
    return proj, trans, band_array


def write_single_tif(filename, im_proj, im_geotrans, im_data):
    if 'int8' in im_data.dtype.name:
        datatype = gdal.GDT_Byte
    elif 'int16' in im_data.dtype.name:
        datatype = gdal.GDT_UInt16
    else:
        datatype = gdal.GDT_Float32

    if len(im_data.shape) == 3:
        im_bands, im_height, im_width = im_data.shape
    else:
        im_bands, (im_height, im_width) = 1, im_data.shape

    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(filename, im_width, im_height, im_bands, datatype,
                            options=["COMPRESS=DEFLATE", "TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512"])

    dataset.SetGeoTransform(im_geotrans)
    dataset.SetProjection(im_proj)
    dataset.SetMetadata("AREA_OR_POINT=Point")

    if im_bands == 1:
        dataset.GetRasterBand(1).WriteArray(im_data)
        dataset.FlushCache
    else:
        for i in range(im_bands):
            dataset.GetRasterBand(i + 1).WriteArray(im_data[i])
            dataset.FlushCache

    del dataset


class solar:
    """
    Object class for handling solar calculations. Many equations are taken from the
    excel sheet at this url : [http://www.esrl.noaa.gov/gmd/grad/solcalc/calcdetails.html]
    It requires a physical location on the earth and a datetime object
    :param lat:             decimal degrees latitude (float OR numpy array)
    :param lon:             decimal degrees longitude (float OR numpy array)
    :param time_zone:       float of time shift from GMT (such as "-5" for EST)
    :param date_time_obj:   either a timestamp string following fmt or a datetime obj
    :param fmt:             if date_time_obj is a string, fmt is required to interpret it
    :param slope:           slope of land at lat,lon for solar energy calculations
    :param aspect:          aspect of land at lat,lon for solar energy calculations
    An instance of this class may have the following attributes:
        =================== =========================================== ========
        attribute           description                                 type
        =================== =========================================== ========
        lat                 latitude                                    (array)
        lon                 longitude                                   (array)
        tz                  time zone                                   (scalar)
        rdt                 reference datetime object (date_time_obj)   (scalar)
        slope               slope, derivative of DEM                    (array)
        aspect              aspect (north is 0, south is 180)           (array)
        ajd                 absolute julian day                         (scalar)
        ajc                 absolute julian century                     (scalar)
        geomean_long        geometric mean longitude of the sun         (scalar)
        geomean_anom        geometric mean longitude anomaly of the sun (scalar)
        earth_eccent        eccentricity of earths orbit                (scalar)
        sun_eq_of_center    the suns equation of center                 (scalar)
        true_long           true longitude of the sun                   (scalar)
        true_anom           true longitude anomaly of the sun           (scalar)
        app_long            the suns apparent longitude                 (scalar)
        oblique_mean_elip   earth oblique mean ellipse                  (scalar)
        oblique_corr        correction to earths oblique elipse         (scalar)
        right_ascension     suns right ascension angle                  (scalar)
        declination         solar declination angle                     (scalar)
        equation_of_time    equation of time (minutes)                  (scalar)
        hour_angle_sunrise  the hour angle at sunrise                   (array)
        solar_noon          LST of solar noon                           (array)
        sunrise             LST of sunrise time                         (array)
        sunset              LST of sunset time                          (array)
        sunlight            LST fractional days of sunlight             (array)
        true_solar          LST for true solar time                     (array)
        hour_angle          total hour angle                            (array)
        zenith              zenith angle                                (array)
        elevation           elevation angle                             (array)
        azimuth             azimuthal angle                             (array)
        rad_vector          radiation vector (distance in AU)           (scalar)
        earth_distance      earths distance to sun in meters            (scalar)
        norm_irradiance     incident solar energy at earth distance     (scalar)
        =================== =========================================== ========
    Units used by this class unless otherwise labeled
      - angle =     degrees
      - distance =  meters
      - energy =    watts or joules
      - time =      mostly in datetime objects. labeled in most cases.
    Planned improvements
        1. DONE. Inputs of numpy arrays for lat and lon needs to be allowed.
        2. inputs of a numpy array DEM for slope/aspect effects on incident solar energy
    Present performance
        To process about one landsat tile (7300^2 matrix) requires 9GB of memory and
        takes 45 seconds to process on a single 3.3GHz thread. It would be nice to get
        the same output to run on ~5GB of memory so a 8GB system could handle it.
    """

    def __init__(self, lat, lon, date_time_obj, time_zone=0,
                 fmt=False, slope=None, aspect=None):
        """
        Initializes critical spatial and temporal information for solar object.
        """
        # empty list of class attributes
        self.ajc = None  # abs julian century (defined on __init__)
        self.ajd = None  # abs julian day (defined on __init__)
        self.app_long = None
        self.atmo_refraction = None
        self.azimuth = None
        self.declination = None
        self.earth_distance = None
        self.earth_eccent = None
        self.elevation = None
        self.elevation_noatmo = None
        self.equation_of_time = None
        self.frac_day = None
        self.geomean_anom = None
        self.geomean_long = None
        self.hour_angle = None
        self.hour_angle_sunrise = None
        self.lat = lat  # lattitude (E positive)- float
        self.lat_r = radians(lat)  # lattitude in radians
        self.lon = lon  # longitude (N positive)- float
        self.lon_r = radians(lon)  # longitude in radians
        self.norm_irradiance = None
        self.oblique_corr = None
        self.oblique_mean_elip = None
        self.rad_vector = None
        self.rdt = None  # reference datetime (defined on __init__)
        self.right_ascension = None
        self.solar_noon = None
        self.solar_noon_time = None
        self.sun_eq_of_center = None
        self.sunlight = None
        self.sunlight_time = None
        self.sunrise = None
        self.sunrise_time = None
        self.sunset = None
        self.sunset_time = None
        self.true_anom = None
        self.true_long = None
        self.true_solar = None
        self.true_solar_time = None
        self.tz = None  # time zone (defined on __init__)
        self.zenith = None
        # slope and aspect
        self.slope = slope
        self.aspect = aspect

        # Constants as attributes
        self.sun_surf_rad = 63156942.6  # radiation at suns surface (W/m^2)
        self.sun_radius = 695800000.  # radius of the sun in meters
        self.orbital_period = 365.2563630  # num of days it takes earth to revolve
        self.altitude = -0.01448623  # altitude of center of solar disk
        # sets up the object with some subfunctions
        self._set_datetime(date_time_obj, fmt, GMT_hour_offset=time_zone)
        # specify if attributes are scalar floats or numpy array floats
        if isinstance(lat, ndarray) and isinstance(lon, ndarray):
            self.is_numpy = True
        else:
            self.is_numpy = False

        return

    def _set_datetime(self, date_time_obj, fmt=False, GMT_hour_offset=0):
        """
        sets the critical time information including absolute julian day/century.
        Accepts datetime objects or a datetime string with format
        :param date_time_obj:   datetime object for time of solar calculations. Will also
                                accept string input with matching value for "fmt" param
        :param fmt:             if date_time_obj is input as a string, fmt allows it to be
                                interpreted
        :param GMT_hour_offset: Number of hours from GMT for timezone of calculation area.
        """
        # if input is datetime_obj set it
        if isinstance(date_time_obj, datetime):
            self.rdt = date_time_obj
            self.rdt += timedelta(hours=-GMT_hour_offset)
        elif isinstance(date_time_obj, str) and isinstance(fmt, str):
            self.rdt = datetime.strptime(date_time_obj, fmt)
            self.rdt += timedelta(hours=-GMT_hour_offset)
        else:
            raise Exception("bad datetime!")
        self.tz = GMT_hour_offset
        # uses the reference day of january 1st 2000
        jan_1st_2000_jd = 2451545
        jan_1st_2000 = datetime(2000, 1, 1, 12, 0, 0)
        time_del = self.rdt - jan_1st_2000
        self.ajd = float(jan_1st_2000_jd) + float(time_del.total_seconds()) / 86400
        self.ajc = (self.ajd - 2451545) / 36525.0

        return

    def get_geomean_long(self):
        """ :return geomean_long: geometric mean longitude of the sun"""
        if not self.geomean_long is None:
            return self.geomean_long

        self.geomean_long = (280.46646 + self.ajc * (36000.76983 + self.ajc * 0.0003032)) % 360
        return self.geomean_long

    def get_geomean_anom(self):
        """calculates the geometric mean anomoly of the sun"""
        if not self.geomean_anom is None:
            return self.geomean_anom
        self.geomean_anom = (357.52911 + self.ajc * (35999.05029 - 0.0001537 * self.ajc))
        return self.geomean_anom

    def get_earth_eccent(self):
        """ :return earth_eccent: precise eccentricity of earths orbit at referece datetime """
        if not self.earth_eccent is None:
            return self.earth_eccent

        self.earth_eccent = 0.016708634 - self.ajc * (4.2037e-5 + 1.267e-7 * self.ajc)

        return self.earth_eccent

    def get_sun_eq_of_center(self):
        """ :return sun_eq_of_center: the suns equation of center"""
        if not self.sun_eq_of_center is None:
            return self.sun_eq_of_center
        if self.geomean_anom is None:
            self.get_geomean_anom()

        ajc = self.ajc
        gma = radians(self.geomean_anom)
        self.sun_eq_of_center = sin(gma) * (1.914602 - ajc * (0.004817 + 0.000014 * ajc)) + \
                                sin(2 * gma) * (0.019993 - 0.000101 * ajc) + \
                                sin(3 * gma) * 0.000289
        return self.sun_eq_of_center

    def get_true_long(self):
        """ :return true_long: the tru longitude of the sun"""
        if not self.true_long is None:
            return self.true_long

        if self.geomean_long is None:
            self.get_geomean_long()

        if self.sun_eq_of_center is None:
            self.get_sun_eq_of_center()
        self.true_long = self.geomean_long + self.sun_eq_of_center
        return self.true_long

    def get_true_anom(self):
        """ :return true_anom: calculates the true anomaly of the sun"""
        if not self.true_anom is None:
            return self.true_anom

        if self.geomean_long is None:
            self.get_geomean_long()

        if self.sun_eq_of_center is None:
            self.get_sun_eq_of_center()

        self.true_anom = self.geomean_anom + self.sun_eq_of_center
        return self.true_anom

    def get_rad_vector(self):
        """ :return rad_vector: incident radiation vector to surface at ref_datetime (AUs)"""
        if not self.rad_vector is None:
            return self.rad_vector

        if self.earth_eccent is None:
            self.get_earth_eccent()
        if self.true_anom is None:
            self.get_true_anom()

        ec = self.earth_eccent
        ta = radians(self.true_anom)

        self.rad_vector = (1.000001018 * (1 - ec ** 2)) / (1 + ec * cos(ta))
        return self.rad_vector

    def get_app_long(self):
        """ :return app_long: calculates apparent longitude of the sun"""
        if not self.app_long is None:
            return self.app_long

        if self.true_long is None:
            self.get_true_long()
        stl = self.true_long
        ajc = self.ajc
        self.app_long = stl - 0.00569 - 0.00478 * sin(radians(125.04 - 1934.136 * ajc))
        return self.app_long

    def get_oblique_mean_elip(self):
        """ :return oblique_mean_elip: oblique mean elliptic of earth orbit """
        if not self.oblique_mean_elip is None:
            return self.oblique_mean_elip

        ajc = self.ajc
        self.oblique_mean_elip = 23 + (26 + (21.448 - ajc * (46.815 + ajc * (0.00059 - ajc * 0.001813))) / 60) / 60
        return self.oblique_mean_elip

    def get_oblique_corr(self):
        """ :return oblique_corr:  the oblique correction """
        if not self.oblique_corr is None:
            return self.oblique_corr

        if self.oblique_mean_elip is None:
            self.get_oblique_mean_elip()

        ome = self.oblique_mean_elip
        ajc = self.ajc

        self.oblique_corr = ome + 0.00256 * cos(radians(125.04 - 1934.136 * ajc))
        return self.oblique_corr

    def get_right_ascension(self):
        """ :return right_ascension: the suns right ascension angle """
        if not self.right_ascension is None:
            return self.right_ascension

        if self.app_long is None:
            self.get_app_long()
        if self.oblique_corr is None:
            self.get_oblique_corr()

        sal = radians(self.app_long)
        oc = radians(self.oblique_corr)
        self.right_ascension = degrees(arctan2(cos(oc) * sin(sal), cos(sal)))
        return self.right_ascension

    def get_declination(self):
        """ :return declination: solar declination angle at ref_datetime"""
        if not self.declination is None:
            return self.declination

        if self.app_long is None:
            self.get_app_long()
        if self.oblique_corr is None:
            self.get_oblique_corr()

        sal = radians(self.app_long)
        oc = radians(self.oblique_corr)

        self.declination = degrees(arcsin((sin(oc) * sin(sal))))
        return self.declination

    def get_equation_of_time(self):
        """ :return equation_of_time: the equation of time in minutes """
        if not self.equation_of_time is None:
            return self.equation_of_time

        if self.oblique_corr is None:
            self.get_oblique_corr()
        if self.geomean_long is None:
            self.get_geomean_long()
        if self.geomean_anom is None:
            self.get_geomean_anom()
        if self.earth_eccent is None:
            self.get_earth_eccent()
        oc = radians(self.oblique_corr)
        gml = radians(self.geomean_long)
        gma = radians(self.geomean_anom)
        ec = self.earth_eccent
        vary = tan(oc / 2) ** 2
        self.equation_of_time = 4 * degrees(vary * sin(2 * gml) - 2 * ec * sin(gma) +
                                            4 * ec * vary * sin(gma) * cos(2 * gml) -
                                            0.5 * vary * vary * sin(4 * gml) -
                                            1.25 * ec * ec * sin(2 * gma))

        return self.equation_of_time

    def get_hour_angle_sunrise(self):
        """ :return hour_angle_sunrise: the hour angle of sunrise """
        if not self.hour_angle_sunrise is None:
            return self.hour_angle_sunrise

        if self.declination is None:
            self.get_declination()
        d = radians(self.declination)
        lat = self.lat_r
        self.hour_angle_sunrise = degrees(arccos((cos(radians(90.833)) /
                                                  (cos(lat) * cos(d)) - tan(lat) * tan(d))))
        return self.hour_angle_sunrise

    def get_solar_noon(self):
        """ :return solar_noon: solar noon in (local sidereal time LST)"""
        if not self.solar_noon is None:
            return self.solar_noon

        if self.equation_of_time is None:
            self.get_equation_of_time()
        lon = self.lon
        eot = self.equation_of_time
        tz = self.tz
        self.solar_noon = (720 - 4 * lon - eot + tz * 60) / 1440
        # format this as a time for display purposes (Hours:Minutes:Seconds)
        if self.is_numpy:
            self.solar_noon_time = timedelta(days=self.solar_noon.mean())
        else:
            self.solar_noon_time = timedelta(days=self.solar_noon)

        return self.solar_noon

    def get_sunrise(self):
        """ :return sunrise: returns the time of sunrise"""
        if not self.sunrise is None:
            return self.sunrise

        if self.solar_noon is None:
            self.get_solar_noon()
        if self.hour_angle_sunrise is None:
            self.get_hour_angle_sunrise()
        sn = self.solar_noon
        ha = self.hour_angle_sunrise
        self.sunrise = (sn * 1440 - ha * 4) / 1440
        # format this as a time for display purposes (Hours:Minutes:Seconds)
        if self.is_numpy:
            self.sunrise_time = timedelta(days=self.sunrise.mean())
        else:
            self.sunrise_time = timedelta(days=self.sunrise)

        return self.sunrise

    def get_sunset(self):
        """ :return sunset: returns the time of sunset"""
        if not self.sunset is None:
            return self.sunset
        if self.solar_noon is None:
            self.get_solar_noon()
        if self.hour_angle_sunrise is None:
            self.get_hour_angle_sunrise()
        sn = self.solar_noon
        ha = self.hour_angle_sunrise

        self.sunset = (sn * 1440 + ha * 4) / 1440
        # format this as a time for display purposes (Hours:Minutes:Seconds)
        if self.is_numpy:
            self.sunset_time = timedelta(days=self.sunset.mean())
        else:
            self.sunset_time = timedelta(days=self.sunset)
        return self.sunset

    def get_sunlight(self):
        """ :return sunlight: amount of daily sunlight in fractional days"""
        if not self.sunlight is None:
            return self.sunlight

        if self.hour_angle_sunrise is None:
            self.get_hour_angle_sunrise()

        self.sunlight = 8 * self.hour_angle_sunrise / (60 * 24)
        # format this as a time for display purposes (Hours:Minutes:Seconds)
        if self.is_numpy:
            self.sunlight_time = timedelta(days=self.sunlight.mean())
        else:
            self.sunlight_time = timedelta(days=self.sunlight)

        return self.sunlight

    def get_true_solar(self):
        """ :return true_solar: true solar time at ref_datetime"""
        if not self.true_solar is None:
            return self.true_solar

        if self.equation_of_time is None:
            self.get_equation_of_time
        lon = self.lon
        eot = self.equation_of_time
        # turn reference datetime into fractional days
        frac_sec = (self.rdt - datetime(self.rdt.year, self.rdt.month, self.rdt.day)).total_seconds()
        frac_hr = frac_sec / (60 * 60) + self.tz
        frac_day = frac_hr / 24
        self.frac_day = frac_day
        # now get true solar time
        self.true_solar = (frac_day * 1440 + eot + 4 * lon - 60 * self.tz) % 1440
        # format this as a time for display purposes (Hours:Minutes:Seconds)
        if self.is_numpy:
            self.true_solar_time = timedelta(days=self.true_solar.mean() / (60 * 24))
        else:
            self.true_solar_time = timedelta(days=self.true_solar / (60 * 24))
        return self.true_solar

    def get_hour_angle(self):
        """ :return hour_angle: returns hour angle at ref_datetime"""
        if not self.hour_angle is None:
            return self.hour_angle

        if self.true_solar is None:
            self.get_true_solar()

        ts = self.true_solar
        # matrix hour_angle calculations
        if self.is_numpy:
            ha = ts
            ha[ha <= 0] = ha[ha <= 0] / 4 + 180
            ha[ha > 0] = ha[ha > 0] / 4 - 180
            self.hour_angle = ha
        # scalar hour_angle calculations
        else:
            if ts <= 0:
                self.hour_angle = ts / 4 + 180
            else:
                self.hour_angle = ts / 4 - 180
        return self.hour_angle

    def get_zenith(self):
        """ :return zenith: returns solar zenith angle at ref_datetime"""
        if not self.zenith is None:
            return self.zenith

        if self.declination is None:
            self.get_declination()
        if self.hour_angle is None:
            self.get_hour_angle()
        d = radians(self.declination)
        ha = radians(self.hour_angle)
        lat = self.lat_r
        self.zenith = degrees(arccos(sin(lat) * sin(d) + cos(lat) * cos(d) * cos(ha)))
        return self.zenith

    def get_elevation(self):
        """ :return elevation: returns solar elevation angle at ref_datetime"""
        if not self.elevation is None:
            return self.elevation

        if self.zenith is None:
            self.get_zenith()

        # perform an approximate atmospheric refraction correction

        # matrix hour_angle calculations
        # these equations are hideous, but im not sure how to improve them without
        # adding computational complexity
        if self.is_numpy:
            e = 90 - self.zenith
            ar = e * 0
            ar[e > 85] = 0
            ar[(e > 5) & (e <= 85)] = 58.1 / tan(radians(e[(e > 5) & (e <= 85)])) - \
                                      0.07 / tan(radians(e[(e > 5) & (e <= 85)])) ** 3 + \
                                      0.000086 / tan(radians(e[(e > 5) & (e <= 85)])) ** 5
            ar[(e > -0.575) & (e <= 5)] = 1735 + e[(e > -0.575) & (e <= 5)] * \
                                          (103.4 + e[(e > -0.575) & (e <= 5)] * (
                                                  -12.79 + e[(e > -0.575) & (e <= 5)] * 0.711))
            ar[e <= -0.575] = -20.772 / tan(radians(e[e <= -0.575]))
        # scalar hour_angle calculations
        else:
            e = 90 - self.zenith
            er = radians(e)

            if e > 85:
                ar = 0
            elif e > 5:
                ar = 58.1 / tan(er) - 0.07 / tan(er) ** 3 + 0.000086 / tan(er) ** 5
            elif e > -0.575:
                ar = 1735 + e * (103.4 + e * (-12.79 + e * 0.711))
            else:
                ar = -20.772 / tan(er)
        self.elevation_noatmo = e
        self.atmo_refraction = ar / 3600
        self.elevation = self.elevation_noatmo + self.atmo_refraction

        return self.elevation

    def get_azimuth(self):
        """ :return azimuth: returns solar azimuth angle at ref_datetime"""
        if not self.azimuth is None:
            return self.azimuth

        if self.declination is None:
            self.get_declination()
        if self.hour_angle is None:
            self.get_hour_angle()
        if self.zenith is None:
            self.get_zenith()

        lat = self.lat_r
        d = radians(self.declination)
        ha = radians(self.hour_angle)
        z = radians(self.zenith)
        # matrix azimuth calculations
        # these equations are hideous monsters, but im not sure how to improve them without
        # adding computational complexity.
        if self.is_numpy:
            az = ha * 0
            az[ha > 0] = (degrees(arccos(
                ((sin(lat[ha > 0]) * cos(z[ha > 0])) - sin(d)) / (cos(lat[ha > 0]) * sin(z[ha > 0])))) + 180) % 360
            az[ha <= 0] = (540 - degrees(
                arccos(((sin(lat[ha <= 0]) * cos(z[ha <= 0])) - sin(d)) / (cos(lat[ha <= 0]) * sin(z[ha <= 0]))))) % 360
            self.azimuth = az
        else:
            if ha > 0:
                self.azimuth = (degrees(arccos(((sin(lat) * cos(z)) - sin(d)) / (cos(lat) * sin(z)))) + 180) % 360
            else:
                self.azimuth = (540 - degrees(arccos(((sin(lat) * cos(z)) - sin(d)) / (cos(lat) * sin(z))))) % 360
        return self.azimuth

    def get_earth_distance(self):
        """
        :return earth_distance: distance between the earth and the sun at ref_datetime
        """
        if self.rad_vector is None:
            self.get_rad_vector()

        # convert rad_vector length from AU to meters
        self.earth_distance = self.rad_vector * 149597870700

        return self.earth_distance

    def get_norm_irradiance(self):
        """
        Calculates incoming solar energy in W/m^2 to a surface normal to the sun.
        inst_irradiance is calculated as = sun_surf_radiance\*(sun_radius / earth_distance)^2
        and is then corrected as a function of solar incidence angle
        :return norm_irradiance: the normal irradiance in W/m^2
        """
        if not self.norm_irradiance is None:
            return self.norm_irradiance

        if self.earth_distance is None:
            self.get_earth_distance()

        ed = self.earth_distance
        # calculate irradiance to normal surface at earth distance
        self.norm_irradiance = self.sun_surf_rad * (self.sun_radius / ed) ** 2

        return self.norm_irradiance

    def get_inc_irradiance(self):
        """
        calculates the actual incident solar irradiance at a given lat,lon coordinate
        with adjustments for slope and aspect if they have been given. Not finished.
        """
        print("this function is unfinished!")
        return

    # def summarize(self):
    #     """ prints attribute list and corresponding values"""
    #     for key in sorted(self.__dict__.iterkeys()):
    #         print("{0} {1}".format(key.ljust(20),sc.__dict__[key]))
    #     return

    def compute_all(self):
        """
        Computes and prints all the attributes of this solar object. Spatial
        averages are printed for numpy array type attributes.
        """
        print("=" * 50)
        print("Interogation of entire matrix of points.")
        print("Some values displayed below are spatial averages")
        print("=" * 50)

        if self.is_numpy:  # print means of lat/lon arrays
            print("latitude, longitude \t{0}, {1}".format(self.lat.mean(), self.lon.mean()))
        else:
            print("latitude, longitude \t{0}, {1}".format(self.lat, self.lon))
        print("datetime \t\t{0} (GMT)".format(self.rdt))
        print("time zone \t\t{0} (GMT offset)".format(self.tz))
        print("")
        print("abs julian day \t\t{0}\t (day)".format(self.ajd))
        print("abs julian century \t{0}\t (cen)".format(self.ajc))
        print("suns geomean long \t{0}\t (deg)".format(self.get_geomean_long()))
        print("suns geomean anom \t{0}\t (deg)".format(self.get_geomean_anom()))
        print("earth eccentricity \t{0}".format(self.get_earth_eccent()))
        print("suns eq of center \t{0}".format(self.get_sun_eq_of_center()))
        print("suns true long \t\t{0}\t (deg)".format(self.get_true_long()))
        print("suns true anom \t\t{0}\t (deg)".format(self.get_true_anom()))
        print("suns apparent long \t{0}\t (deg)".format(self.get_app_long()))
        print("earth obliq mean elip \t{0}\t (deg)".format(self.get_oblique_mean_elip()))
        print("earth obliq correction\t{0}\t (deg)".format(self.get_oblique_corr()))
        print("sun right ascension \t{0}\t (deg)".format(self.get_right_ascension()))
        print("solar declination angle {0}\t (deg)".format(self.get_declination()))
        print("equation of time \t{0}\t (min)".format(self.get_equation_of_time))

        if self.is_numpy:  # print means of hour angle array
            print("hour angle sunrise\t{0}\t (deg)".format(self.get_hour_angle_sunrise().mean()))
        else:
            print("hour angle sunrise\t{0}\t (deg)".format(self.get_hour_angle_sunrise()))

        print("")
        self.get_solar_noon()
        print("solar noon \t\t{0}\t (HMS - LST)".format(self.solar_noon_time))
        self.get_sunrise()
        print("sunrise \t\t{0}\t (HMS - LST)".format(self.sunrise_time))
        self.get_sunset()
        print("sunset  \t\t{0}\t (HMS - LST)".format(self.sunset_time))
        self.get_sunlight()
        print("sunlight durration \t{0}\t (HMS)".format(self.sunlight_time))
        self.get_true_solar()
        print("true solar time \t{0}\t (HMS - LST)".format(self.true_solar_time))
        print("")
        if self.is_numpy:  # print means of these array objects
            print("hour angle \t\t{0}\t (deg)".format(self.get_hour_angle().mean()))
            print("solar zenith angle \t{0}\t (deg)".format(self.get_zenith().mean()))
            print("solar elevation angle \t{0}\t (deg)".format(self.get_elevation().mean()))
            print("solar azimuth angle \t{0}\t (deg)".format(self.get_azimuth().mean()))
        else:
            print("hour angle \t\t{0}\t (deg)".format(self.get_hour_angle()))
            print("solar zenith angle \t{0}\t (deg)".format(self.get_zenith()))
            print("solar elevation angle \t{0}\t (deg)".format(self.get_elevation()))
            print("solar azimuth angle \t{0}\t (deg)".format(self.get_azimuth()))
        print("")
        print("radiation vector \t{0}\t (AU)".format(self.get_rad_vector()))
        print("earth sun distance \t{0}(m)".format(self.get_earth_distance()))
        print("norm irradiance \t{0}\t (W/m*m)".format(self.get_norm_irradiance()))
        print("=" * 50)


# # testing
# if __name__ == "__main__":
#     # use the current time and my time zone
#     my_datestamp   = "20150515-120000"     # date stamp
#     my_fmt         = "%Y%m%d-%H%M%S"       # datestamp format
#     my_tz          = -4                    # timezone (GMT/UTC) offset
#     my_lat = 37                            # lat (N positive)
#     my_lon = -76.4                         # lon (E positive)
#
#     sc  = solar(my_lat, my_lon, my_datestamp, my_tz, my_fmt)
#     sc.compute_all()
#     sc.summarize()


class landsat_metadata:
    """
    A landsat metadata object. This class builds is attributes
    from the names of each tag in the xml formatted .MTL files that
    come with landsat data. So, any tag that appears in the MTL file
    will populate as an attribute of landsat_metadata.
    You can access explore these attributes by using, for example
    .. code-block:: python
        from dnppy import landsat
        meta = landsat.landsat_metadata(my_filepath) # create object
        from pprint import pprint                    # import pprint
        pprint(vars(m))                              # pretty print output
        scene_id = meta.LANDSAT_SCENE_ID             # access specific attribute
    :param filename: the filepath to an MTL file.
    """

    def __init__(self, filename):
        """
        There are several critical attributes that keep a common
        naming convention between all landsat versions, so they are
        initialized in this class for good record keeping and reference
        """
        # custom attribute additions
        self.FILEPATH = filename
        self.DATETIME_OBJ = None
        # product metadata attributes
        self.LANDSAT_SCENE_ID = None
        self.DATA_TYPE = None
        self.ELEVATION_SOURCE = None
        self.OUTPUT_FORMAT = None
        self.SPACECRAFT_ID = None
        self.SENSOR_ID = None
        self.WRS_PATH = None
        self.WRS_ROW = None
        self.NADIR_OFFNADIR = None
        self.TARGET_WRS_PATH = None
        self.TARGET_WRS_ROW = None
        self.DATE_ACQUIRED = None
        self.SCENE_CENTER_TIME = None
        # image attributes
        self.CLOUD_COVER = None
        self.IMAGE_QUALITY_OLI = None
        self.IMAGE_QUALITY_TIRS = None
        self.ROLL_ANGLE = None
        self.SUN_AZIMUTH = None
        self.SUN_ELEVATION = None
        self.EARTH_SUN_DISTANCE = None  # calculated for Landsats before 8.
        # read the file and populate the MTL attributes
        self._read(filename)

    def _read(self, filename):
        """ reads the contents of an MTL file """
        # if the "filename" input is actually already a metadata class object, return it back.
        if inspect.isclass(filename):
            return filename
        fields = []
        values = []
        metafile = open(filename, 'r')
        metadata = metafile.readlines()
        for line in metadata:
            # skips lines that contain "bad flags" denoting useless data AND lines
            # greater than 1000 characters. 1000 character limit works around an odd LC5
            # issue where the metadata has 40,000+ characters of whitespace
            bad_flags = ["END", "GROUP"]
            if not any(x in line for x in bad_flags) and len(line) <= 1000:
                try:
                    line = line.replace("  ", "")
                    line = line.replace("\n", "")
                    field_name, field_value = line.split(' = ')
                    fields.append(field_name)
                    values.append(field_value)
                except:
                    pass
        for i in range(len(fields)):
            # format fields without quotes,dates, or times in them as floats
            if not any(['"' in values[i], 'DATE' in fields[i], 'TIME' in fields[i]]):
                setattr(self, fields[i], float(values[i]))
            else:
                values[i] = values[i].replace('"', '')
                setattr(self, fields[i], values[i])
        # create datetime_obj attribute (drop decimal seconds)
        dto_string = self.DATE_ACQUIRED + self.SCENE_CENTER_TIME
        self.DATETIME_OBJ = datetime.strptime(dto_string.split(".")[0], "%Y-%m-%d%H:%M:%S")
        # only landsat 8 includes sun-earth-distance in MTL file, so calculate it
        # for the Landsats 4,5,7 using solar module.
        if not self.SPACECRAFT_ID == "LANDSAT_8":
            # use 0s for lat and lon, sun_earth_distance is not a function of any one location on earth.
            s = solar(0, 0, self.DATETIME_OBJ, 0)
            self.EARTH_SUN_DISTANCE = s.get_rad_vector()
        print("Scene {0} center time is {1}".format(self.LANDSAT_SCENE_ID, self.DATETIME_OBJ))


if __name__ == '__main__':
    # a = "LC08_L1TP_083014_20160324_B5"
    # print(a[:27])
    # start_time = time.time()
    read_wait_dirs(host_name, port, password, band_nums, key_name, fail_key, success_key)
    # print(time.time() - start_time)

