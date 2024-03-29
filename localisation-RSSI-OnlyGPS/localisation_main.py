#! /usr/bin/python3

from localisation_balloons import balloon_main
from navpy import lla2ned
import socket, sys
from _thread import *
from threading import Thread
import threading
import numpy as np
import csv
from datetime import datetime
import time
import os
import re
import math
import GlobalVals

sys.path.insert(1,'../utils')
from navpy import lla2ned
from common import *
from common_class import *
import copy



def rssi_update(new_data):
    sysID = new_data.sysID
    targetID = new_data.targetPayloadID

    GlobalVals.RSSI_MATRIX[sysID-1][targetID-1] = new_data

def position_update(posXYZ,new_gps):
    i = sysID_to_index(new_gps.sysID)
    GlobalVals.POS_XYZ[i-1]=posXYZ
    GlobalVals.GPS_ALL[i-1]=new_gps


def gps_callback(host,port):

    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    
    while True:
        try:        
            s.connect((host,port))
            s.settimeout(GlobalVals.GPS_TIMEOUT)
        except Exception as e:
            if e.args[1] == 'Connection refused':
                print('Retry connecting to GPS....')
                time.sleep(1)
                continue
            else:
                print("Exception: " + str(e.__class__))
                print("There was an error starting the GPS socket. This thread will now stop.")
                with GlobalVals.BREAK_GPS_THREAD_MUTEX:
                    GlobalVals.BREAK_GPS_THREAD = True
                return 
        break

    while True:
        with GlobalVals.BREAK_GPS_THREAD_MUTEX:
            if GlobalVals.BREAK_GPS_THREAD:
                break

        try:
            data_bytes = s.recv(GlobalVals.GPS_BUFFER)
        except Exception as e:
            print("Exception: " + str(e.__class__))
            print("There was an error starting the GPS receiver socket. This thread will now stop.")
            break

        if len(data_bytes) == 0:
            continue

        data_str = data_bytes.decode('utf-8')
        
        string_list = []
        string_list = extract_str_btw_curly_brackets(data_str)
        # print("GPS string list: ",string_list)
        if len(string_list) > 0:
            gps_list = []
            for string in string_list:
                received, gps_i = stringToGPS(string)
                if received:
                    gps_list.append(gps_i)
            
            idx = 0
            
            with GlobalVals.GPS_UPDATE_MUTEX:
                while idx < len(gps_list):
                    ned = lla2ned(gps_list[idx].lat, gps_list[idx].lon, gps_list[idx].alt, GlobalVals.GPS_REF.lat, GlobalVals.GPS_REF.lon, GlobalVals.GPS_REF.alt)
                    posXYZ = POS_XYZ(ned[0],ned[1])   
                    position_update(posXYZ, gps_list[idx])
                    idx += 1

    s.close()

def distanceRSSI_callback(host,port):

    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    while True:
        try:        
            s.connect((host,port))
            s.settimeout(GlobalVals.RSSI_TIMEOUT)
        except Exception as e:
            if e.args[1] == 'Connection refused':
                print('Retry connecting to RSSI....')
                time.sleep(1)
                continue
            else:
                print("Exception: " + str(e.__class__))
                print("There was an error starting the RSSI socket. This thread will now stop.")
                with GlobalVals.BREAK_RSSI_THREAD_MUTEX:
                    GlobalVals.BREAK_RSSI_THREAD = True
                return 
        break

    while True:
        with GlobalVals.BREAK_RSSI_THREAD_MUTEX:
            if GlobalVals.BREAK_RSSI_THREAD:
                break

        try:
            data_bytes = s.recv(GlobalVals.RSSI_BUFFER)
        except Exception as e:
            print("Exception: " + str(e.__class__))
            print("There was an error starting the RSSI receiver socket. This thread will now stop.")
            break
        
        # print("ID",balloon_id,"Received RSSI: ",data_bytes)

        if len(data_bytes) == 0:
            continue
        
        data_str = data_bytes.decode('utf-8')
        # print('data RSSI: ',data_str)
        string_list = extract_str_btw_curly_brackets(data_str)
        # print(data_str)
        #print("RSSI string:", string_list)
        if len(string_list) > 0:
            rssi_list = []
            for string in string_list:
                received, rssi_i = stringToRSSI(string)
                
                if received:
                    rssi_list.append(rssi_i)
            
            idx = 0
            with GlobalVals.RSSI_UPDATE_MUTEX:
                while idx < len(rssi_list):
                    # print('updating RSSI')
                    # print(rssi_list[idx].distance)
                    rssi_update(rssi_list[idx])
                    # print(rssi_list[idx].epoch, rssi_list[idx].rssi_filtered)
                    idx += 1
            # print('----------------------------')
    s.close()
    


if __name__ == "__main__":
    
    print("Localisation node started ...")

    numArgs = len(sys.argv)

    if numArgs == 2:
        GlobalVals.SYSID = int(sys.argv[1])

    GPS_Thread = Thread(target=gps_callback,args=(GlobalVals.HOST,GlobalVals.PORT_GPS))
    GPS_Thread.start()

    # RSSIThread = Thread(target=distanceRSSI_callback, args = (GlobalVals.HOST, GlobalVals.PORT_RSSI))
    # RSSIThread.start()
    

    leader = GlobalVals.LEADER #any anchor                      
    sigma_range_measurement_val = GlobalVals.SIGMA_RSSI_RANGE     # this depends on the real data

    loopTime = GlobalVals.LOOP_TIME                 

    try:
        os.makedirs("../datalog")
    except FileExistsError:
        pass

    file_name = "../datalog/"+time.strftime("%Y%m%d-%H%M%S")+"-localisationRSSI.txt"

    logString = "px1, py1, px2, py2, px3, py3, px4, py4, px5, py5, lx1, ly1,lx2, ly2, lx3, ly3, lx4, ly4, lx5,ly5, iteration, execution time, epoch,  gps1lat, gps1lon, gps2lat, gps2lon, gps3lat, gps3lon, gps4lat, gps4lon,gps5lat,gps5lon,rssi12, rssi13, rssi21, rssi23, rssi31, rssi32 ,distanceMatrix01,distanceMatrix02,distanceMatrix10,distanceMatrix12,distanceMatrix20,distanceMatrix21\n"
    
    try:
        fileObj = open(file_name, "a")
        fileObj.write(logString)
        fileObj.close()
    except Exception as e:
        print("Localisation: Error writting to file. Breaking thread.")
        print("Localisation: Exception: " + str(e.__class__))


    
    # Logging
    location = GlobalVals.POS_XYZ

    time.sleep(10)

    print("Reading GPS signals ...")
    while True:
        if checkAllGPS(GlobalVals.GPS_ALL):
            break
    
    print("Algorithm started ....")

    sysID = GlobalVals.SYSID
    while True:
        timeLoopStart = time.time()

        with GlobalVals.GPS_UPDATE_MUTEX:
            posXYZ_tmp = copy.deepcopy(GlobalVals.POS_XYZ)
            gps_tmp = copy.deepcopy(GlobalVals.GPS_ALL)
       
        with GlobalVals.RSSI_UPDATE_MUTEX:
            rssiAll = copy.deepcopy(GlobalVals.RSSI_MATRIX)

        # Main loop
        start_time = time.time()
        location,_,iteration = balloon_main(leader,GlobalVals.ANCHOR_LIST,posXYZ_tmp,sigma_range_measurement_val)
        execution_time = time.time()-start_time
        
        pos_error = np.zeros([GlobalVals.N_BALLOON,2])
        for i in range(GlobalVals.N_BALLOON):
            pos_error[i,:] = [location[i,0]-posXYZ_tmp[i].x, location[i,1]-posXYZ_tmp[i].y]

        print('----- start printing ------')
        print('Time: ', start_time)
        print("Balloon 1: lat", round(gps_tmp[0].lat,4), "lon: ", round(gps_tmp[0].lon,4))
        print("Balloon 2: lat", round(gps_tmp[1].lat,4), "lon: ", round(gps_tmp[1].lon,4))

        print("localisation error: \n", pos_error)
        logString = list_to_str([posXYZ_tmp[0].x, posXYZ_tmp[0].y,posXYZ_tmp[1].x, posXYZ_tmp[1].y, posXYZ_tmp[2].x, posXYZ_tmp[2].y, posXYZ_tmp[3].x, posXYZ_tmp[3].y, posXYZ_tmp[4].x, posXYZ_tmp[4].y,location[0,0],location[0,1],location[1,0],location[1,1],location[2,0],location[2,1],location[3,0],location[3,1],location[4,0],location[4,1], iteration,execution_time, start_time, gps_tmp[0].lat, gps_tmp[0].lon, gps_tmp[1].lat, gps_tmp[1].lon, gps_tmp[2].lat, gps_tmp[2].lon, gps_tmp[3].lat, gps_tmp[3].lon, gps_tmp[4].lat, gps_tmp[4].lon,rssiAll[0][1].distance,rssiAll[0][2].distance,rssiAll[1][0].distance,rssiAll[1][2].distance,rssiAll[2][0].distance,rssiAll[2][1].distance,distanceMatrix[0][1],distanceMatrix[0][2],distanceMatrix[1][0],distanceMatrix[1][2],distanceMatrix[2][0],distanceMatrix[2][1]])
        
        try:
            fileObj = open(file_name, "a")
            fileObj.write(logString)
            fileObj.close()
        except Exception as e:
            print("Localisation-RSSI: Error writting to file. Breaking thread.")
            print("Localisation-RSSI: Exception: " + str(e.__class__))
            break
        
        elapsed = time.time()-timeLoopStart
        if elapsed > loopTime:
            continue
        else:
            time.sleep(loopTime-elapsed)

    if GPS_Thread.is_alive():
        with GlobalVals.BREAK_GPS_THREAD_MUTEX:
            GlobalVals.BREAK_GPS_THREAD = True
        GPS_Thread.join()

    # if RSSIThread.is_alive():
    #     with GlobalVals.BREAK_RSSI_THREAD_MUTEX:
    #         GlobalVals.BREAK_RSSI_THREAD = True
    #     RSSIThread.join()

