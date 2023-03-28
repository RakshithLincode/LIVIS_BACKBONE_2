from common.utils import CacheHelper
from django.http import response
import inspection
import numpy as np
import cv2 
from numpy import append, array
import json
import base64
import multiprocessing
import sys
from pymongo import MongoClient
from bson import ObjectId
from livis import settings as settings
from livis.settings import BASE_URL
import os
import time
import datetime
from inspection import plc_controller
from common.utils import *



# def singleton(cls):
#     instances = {}
#     def getinstance():
#         if cls not in instances:
#             instances[cls] = cls()
#         return instances[cls]
#     return getinstance


# @singleton
# class MongoHelper:
#     client = None
#     def __init__(self):
#         if not self.client:
#             self.client = MongoClient(host='localhost', port=27017)

#         self.db = self.client[settings.MONGO_DB]
#         if settings.DEBUG:
#             self.db.set_profiling_level(2)
#         # placeholder for filter
#     """
#     def getDatabase(self):
#         return self.db
#     """

#     def getCollection(self, cname, create=False, codec_options=None):
#         _DB = "BHATTAM"
#         DB = self.client[_DB]
#         return DB[cname]

#@singleton
class CurrentPart:
    def __init__(self, part_name, part_id):
        self.part_name = part_name
        self.part_id = part_id
        self.status = None
        self.cam_view = None
        self.predictions_list = []
        self.reject_reasons = []
        self.defects_dict = {}

    def check_defects(self):
        json_file_path = str(self.part_name)+"_kanban.json"
        f = open("D:\\pro\\backend\\livis-be\\Indo_mim_tirupathi\\republic\\livis\\inspection\\"+json_file_path, "r")
        kanban_dict = json.loads(f.read())
        predicted_dict = self.list_to_dict()
        if len(predicted_dict)> 0:
                kanban_for_view_list = kanban_dict["view"+str(self.cam_view)]
                for item in kanban_for_view_list:
                    for key, value in predicted_dict.items():
                        if item.get("defect_name") == key:
                            self.status = "Rejected"
                            if key != self.part_name or key!="damler" or key!="scania" or key!="cum40":
                                if key not in [self.part_name, "damler", "scania","cum40"]:
                                    [self.reject_reasons.append(key) for cnt in range(value)]
                            
        if len(self.reject_reasons) == 0:
            self.status = "Accepted"
        return 0

    def check_features(self):
        json_file_path = str(self.part_name) + "_kanban.json"
        f = open("D:\\pro\\backend\\livis-be\\Indo_mim_tirupathi\\republic\\livis\\inspection\\"+json_file_path, "r")

        kanban_dict = json.loads(f.read())
        predicted_dict = self.list_to_dict()
        kanban_for_view_list = kanban_dict["view"+str(self.cam_view)]
        #print("checking for features", kanban_for_view_list)
        for item in kanban_for_view_list:
            feature_found = 0
            for key, value in predicted_dict.items():
                if item.get("feature_name") == key:
                    feature_found = 1
                    if item.get("count")!= value:
                        self.status = "Rejected"
                        self.reject_reasons.append(key+" count mismatch")
                        #return 0
            if feature_found == 0 and item.get("feature_name"):
                self.status = "Rejected"
                self.reject_reasons.append(item.get("feature_name").replace('hole_presence','21_hole_absence'))
            

        return 0

    def list_to_dict(self):
        predicted_dict = {}
        for i in self.predictions_list:
            if predicted_dict.get(i):
                predicted_dict[i] +=1
            else:
                predicted_dict[i] = 1
        return predicted_dict


def start_process_util(data):
    part_name = data.get('part_name',None)
    operator_name = data.get('fName',None)
    user_role = data.get('role',None)
    user_id = data.get('user_id',None)
    print(part_name,'fffffffffffffffffffffffffffffffffffffffffffffffff')
    print(type(part_name))
    CacheHelper().set_json({'current_part_name':part_name})
    CacheHelper().set_json({"operator_name":operator_name})
    CacheHelper().set_json({"user_role":user_role})
    CacheHelper().set_json({"operator_id":user_id})
    CacheHelper().set_json({"mask_frame":None})
    CacheHelper().set_json({"measure_frame":None})
    print(part_name,' from start proceess util')
    if part_name is None:
        return "part name not present", 200
    mp = MongoHelper().getCollection('inspection', None)
    current_date = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    createdAt = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    coll = {
    "part_name":part_name,
    "start_time":createdAt,
    "end_time":"",
    "operator_id":user_id,
    "operator_name":operator_name,
    "user_role":user_role,
    "produced_on":current_date,
    "status":"started",
    }
    curr_insp_id = mp.insert_one(coll)
    ret = mp.find_one({'_id':curr_insp_id.inserted_id})
    response = {"_id":ret["_id"]}
    bb = MongoHelper().getCollection('current_inspection')
    ps = bb.find_one()
    if ps is None:
        bb.insert_one({'current_inspection_id' : str(curr_insp_id.inserted_id)})
    else:
        ps['current_inspection_id'] = str(curr_insp_id.inserted_id)
        bb.update_one({"_id" : ps['_id']}, {"$set" : ps})
    response = {"current_inspection_id":curr_insp_id.inserted_id, "part_name": part_name}
    return response,200

def save_inspection(data):
    inspection_id = data.get('inspection_id', None)
    mp = MongoHelper().getCollection(str(inspection_id))
    docs = [i for i in mp.find({"consolidated":False})]
    results = {}
    status = None
    results["inference_images"] = []
    results["input_images"] = []
    results["mask_frame"] = []
    results["measure_frame"] = []
    results["reasons"] = {}
    results["defect_list"] = []
    reasons_dict ={}
    if len(docs) != 21:
        status = "Rejected"
    for doc in docs:
        print("****************************#######################")
        print(doc)
        if doc["status"] == "Rejected":
            status = "Rejected"
            results["defect_list"].append(doc["defects"])
        results["inference_images"].append(doc["inference_image"])
        results["input_images"].append(doc["input_image"])
        results["mask_frame"].append(doc["mask_frame"])
        results["measure_frame"].append(doc["measure_frame"])
        for key, value in doc["reason"].items():
            if reasons_dict.get(key):
                reasons_dict[key] += value
            else:
                reasons_dict[key] = value 
            
        doc["consolidated"] = True
        doc['flagged'] = False
        mp.update({'_id' : doc['_id']}, {"$set" : doc})
    if not status:
        status = "Accepted"
    results["status"] = status
    results['time_stamp'] = str(datetime.datetime.now().replace(microsecond=0))
    str_ = ""
    for key, value in reasons_dict.items():
        if key == "Part mismatch" or key =="21_hole_absence": 
            value = 1
        results["reasons"][key] = value 
    print(" ********* Results are*****************")
    print(results)
    mp = MongoHelper().getCollection(str(inspection_id)+"_results")
    mp.insert_one(results)
    return status
        
def get_data_feed(topic):
    b= CacheHelper().get_json(topic)
    result = b
    return result

def get_single_frame(topic):
    frame = CacheHelper().get_json(topic)
    return frame

def create_urls_from_camera(camera_id, BASE_URL):
    fmt_url = BASE_URL + '/livis/v1/inspection/get_output_stream/{}/' 
    return fmt_url.format(camera_id)

def get_running_process_utils():
    mp = MongoHelper().getCollection('inspection')
    insp_coll = [i for i in mp.find({"status":"started"})]
    response = {}
    if len(insp_coll) > 0:
        res = insp_coll[-1]
        response["inspection_id"] = str(res['_id'])
        response["part_name"] = res["part_name"]
    return response,200

def end_process_util(data):
    """
        Usage:  Ending  the inspection process by updating the status as completed, with the end time
        Request Parameters: {
                    "inspection_id":"61d4257708f3e625aa6b3b26"
                    }
        Request Method: POST
        Response: {
                    "part_id": "61d4257708f3e625aa6b3b26"
                    "workstation_id": "6392257708f3e625aa6b3b26",
                    "plan_id":plan_id,
                    "start_time": "10:00:00",
                    "end_time":"11:00:00",
                    "shift_id":shift_id,
                    "operator_id":operator_id,
                    "produced_on":current_date,
                    "status":"completed",
                    "inference_urls" : ["url1","url2"]
                    }

        """
    CacheHelper().set_json({"input_frame_path":None})
    CacheHelper().set_json({"mask_frame":None})
    CacheHelper().set_json({"measure_frame":None})
    CacheHelper().set_json({"inference_frame":None})
    CacheHelper().set_json({"status":None})
    CacheHelper().set_json({"defects":None})
    CacheHelper().set_json({"ocr_barcode_mismatch":None})
    CacheHelper().set_json({"label_angle":None})
    CacheHelper().set_json({"label_to_sealent_measurment":None})
    CacheHelper().set_json({'current_part_name':None})
    CacheHelper().set_json({"feature_mismatch":None})
    mp = MongoHelper().getCollection('current_inspection')
    doc = mp.find_one()
    if doc:
        inspection_id = doc["current_inspection_id"]
    endedAt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colle = {
    "status" : "completed",
    "end_time" : endedAt
    }
    mp = MongoHelper().getCollection('inspection')
    dataset = mp.find_one({'_id' : ObjectId(inspection_id)})
    mp.update_one({'_id' : ObjectId(dataset['_id'])}, {'$set' :  colle})
    bb = MongoHelper().getCollection('current_inspection')
    ps = bb.find_one()
    if ps is None:
        bb.insert_one({'current_inspection_id': None})
    else:
        ps['current_inspection_id'] = None
        bb.update_one({"_id": ps['_id']}, {"$set": ps})
    return {},200

def get_defect_list(inspectionid):
    retry_inspection = CacheHelper().get_json("retry_inspection")
    mp = MongoHelper().getCollection( str(inspectionid) + '_results')
    camera = CacheHelper().get_json('camera_health_check')
    plc = CacheHelper().get_json('plc_health_check')
    dataset = [p for p in mp.find().sort( "$natural", -1 )]
    dataset1 = [p for p in mp.find({"status":"Accepted"})]
    dataset2 = [p for p in mp.find({"status":"Rejected"})]
    total_production = len(dataset)
    total_accepted_count = len(dataset1)
    total_rejected_count = len(dataset2)
    try:
        retry_count = [i for i in mp.find().sort([( '_id', -1)]).limit(1)]
        retry_count_id = retry_count[0]['_id']
        retry_count_value = mp.find_one({'_id' :ObjectId(retry_count_id)})
        retry_count = retry_count_value['retry_count']
        print(retry_count,'retry_count')
    except Exception as e:
        print(e)	
    plc_trigger = CacheHelper().get_json("inspection_trigger")    
    if len(dataset) > 0:
        dataset = dataset[0]
        dataset['total'] = str(total_production)
        dataset['total_accepted'] = str(total_accepted_count)
        dataset['total_rejected'] = str(total_rejected_count)
        dataset['camera'] = True
        dataset['plc'] = True
        if plc_trigger == True:
            dataset['plc_trigger'] = 'True'
        else:
            dataset['plc_trigger'] = 'False'
        if "None" in dataset['label_angle'] or retry_count  >= 1 :
            dataset['label_angle'] = []
            dataset['retry'] = 'False'
        else:
            dataset['retry'] = 'True'
        if retry_inspection == True:
            dataset['retry_inspection'] = 'True'
        else:
            dataset['retry_inspection'] = 'False'
        if None in dataset['label_to_sealent_measurment']:
            dataset['label_to_sealent_measurment'] = []
    else:
        part_name = CacheHelper().get_json('part_name')
        dataset = {'part_name':part_name}
        dataset['camera'] = True
        dataset['plc'] = True
    return dataset, 200 

def get_inference_feed(cam_id):
    print(cam_id)
    key = str(cam_id)
    while True:
        v = CacheHelper().get_json(key)
        im_b64_str = v
        ret, jpeg = cv2.imencode('.jpg', im_b64_str)
        frame = jpeg.tobytes()
    
        yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
    

def get_metrics_util(inspection_id):
    """
        Usage: Return the report of the the current inspection happening, that is stored in database. This information
            is used in the operator panel dashboard to convey to the user the current inspection process results.
        Request Parameters: {
                            "inspection_id": "6224257708f3e625aa6b3b26"
                            }
        Request Method: GET
        Response: {
                    "part_id": "61d4257708f3e625aa6b3b26"
                    "workstation_id": "6392257708f3e625aa6b3b26",
                    "plan_id":plan_id,
                    "start_time":createdAt,
                    "end_time":"",
                    "shift_id":shift_id,
                    "operator_id":operator_id,
                    "produced_on":current_date,
                    "status":"started",
                    "inference_urls" : ["url1","url2"],
                    "duration":"",
                    "total_accpeted":100,
                    "total_rejected":10,
                    "total":110
                }
        """
    mp = MongoHelper().getCollection( str(inspection_id) + '_results')
    dataset = [p for p in mp.find().sort( "$natural", -1 )]
    dataset1 = [p for p in mp.find({"status":"Accepted"})]
    dataset2 = [p for p in mp.find({"status":"Rejected"})]
    total_production = len(dataset)
    total_accepted_count = len(dataset1)
    total_rejected_count = len(dataset2)
    if len(dataset) > 0:
        dataset = dataset[0]
        dataset['total'] = str(total_production)
        dataset['total_accepted'] = str(total_accepted_count)
        dataset['total_rejected'] = str(total_rejected_count)
    else:
        part_name = CacheHelper().get_json('current_part_name')
        dataset = {'part_name':part_name}
    return dataset, 200

def save_inspection_details_util(data):
    inspection_id = data.get('current_inspection_id',None)
    input_frame = CacheHelper().get_json("input_frame_path")
    mask_frame = CacheHelper().get_json("mask_frame")
    measure_frame = CacheHelper().get_json("measure_frame")
    inference_frame = CacheHelper().get_json("inference_frame")
    status = CacheHelper().get_json("status")
    defects = CacheHelper().get_json("defects")
    ocr_barcode_mismatch = CacheHelper().get_json("ocr_barcode_mismatch")
    label_angle = CacheHelper().get_json("label_angle")
    label_to_sealent_measurment = CacheHelper().get_json("label_to_sealent_measurment")
    part_name =  CacheHelper().get_json('current_part_name')
    feature_mismatch = CacheHelper().get_json("feature_mismatch")
    operator_name = CacheHelper().get_json("operator_name")
    user_role = CacheHelper().get_json("user_role")
    operator_id = CacheHelper().get_json("operator_id")
    mp = MongoHelper().getCollection(str(inspection_id)+"_results")
    retry_count = 0
    inspection_details = {
        "input_frame": input_frame,
        "mask_frame": mask_frame,
        "measure_frame": measure_frame,
        "inference_frame": inference_frame,
        "status": status,
        "defects": defects,
        "feature_mismatch":feature_mismatch,
        "ocr_barcode_mismatch":ocr_barcode_mismatch,
        "label_angle":label_angle,
        "label_to_sealent_measurment":label_to_sealent_measurment,
        "created_at":datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        'time_stamp': str(datetime.datetime.now().replace(microsecond=0)),
        "part_name": part_name,
        "operator_name":operator_name,
        "user_role":user_role,
        "operator_id":operator_id,
        "is_flag":False,
        "flag_message":None,
        "retry":False,
        "retry_count": retry_count,
    }
    print(inspection_details,'inspection_details')
    try:
        mp = MongoHelper().getCollection(str(inspection_id)+"_results")
        _id = mp.insert_one(inspection_details)
        return "success",200
    except Exception as e:
        print(e)
        return "Object not available", 400

def save_retry_details_util(data):
    inspection_id = data.get('current_inspection_id',None)
    input_frame = CacheHelper().get_json("input_frame_path")
    mask_frame = CacheHelper().get_json("mask_frame")
    measure_frame = CacheHelper().get_json("measure_frame")
    inference_frame = CacheHelper().get_json("inference_frame")
    status = CacheHelper().get_json("status")
    defects = CacheHelper().get_json("defects")
    ocr_barcode_mismatch = CacheHelper().get_json("ocr_barcode_mismatch")
    label_angle = CacheHelper().get_json("label_angle")
    label_to_sealent_measurment = CacheHelper().get_json("label_to_sealent_measurment")
    part_name =  CacheHelper().get_json('current_part_name')
    feature_mismatch = CacheHelper().get_json("feature_mismatch")
    operator_name = CacheHelper().get_json("operator_name")
    user_role = CacheHelper().get_json("user_role")
    operator_id = CacheHelper().get_json("operator_id")
    mp = MongoHelper().getCollection(str(inspection_id)+"_results")
    try:
        retry_count = [i for i in mp.find().sort([( '_id', -1)]).limit(1)]
        retry_count_id = retry_count[0]['_id']
        retry_count_value = mp.find_one({'_id' :ObjectId(retry_count_id)})
        retry_count = retry_count_value['retry_count']
        retry_count = int(retry_count) + 1
    except Exception as e:
        print(e)		
    retry_details = {
        "input_frame": input_frame,
        "mask_frame": mask_frame,
        "measure_frame": measure_frame,
        "inference_frame": inference_frame,
        "status": status,
        "defects": defects,
        "feature_mismatch":feature_mismatch,
        "ocr_barcode_mismatch":ocr_barcode_mismatch,
        "label_angle":label_angle,
        "label_to_sealent_measurment":label_to_sealent_measurment,
        "created_at":datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        'time_stamp': str(datetime.datetime.now().replace(microsecond=0)),
        "part_name": part_name,
        "operator_name":operator_name,
        "user_role":user_role,
        "operator_id":operator_id,
        "is_flag":False,
        "flag_message":None,
        "retry":True,
        "retry_count": retry_count,
        }
    try:
        mp_data = mp.find_one()
        value = [i for i in mp.find().sort([( '_id', -1)]).limit(1)]
        _id_new = value[0]['_id']
        if mp_data is None:
            mp.insert_one(retry_details)
        else:
            mp.update_one({'_id' :ObjectId(_id_new)}, {"$set" : retry_details})
        CacheHelper().set_json({"retry_inspection":False})
        return "success",200	
    except Exception as e:
        print(e)		
        return "Object not available", 400		

def start_inspection_util(data):
    inspection_id = data.get("inspection_id",None)
    part_name = data.get("part_name",None)
    try:
        message = "Inspection starts"
        CacheHelper().set_json({"inspection_trigger":True})
        status_code = 200
    except:
        message = "Inspection is not started"
        status_code = 403
    return message,status_code

def retry_inspection_util():
    try:
        message = "Retry Inspection starts"
        CacheHelper().set_json({"inspection_trigger":True})
        CacheHelper().set_json({"retry":True})
        CacheHelper().set_json({"retry_inspection":True})
        status_code = 200
    except:
        message = "Error in Retry Inspection is not started"
        status_code = 403
    return message,status_code

def set_config_util(data):
    top_value = data.get('top')
    bottom_value = data.get('bottom')
    left_value = data.get('left')
    right_value = data.get('right')
    pay_load_data = {
        "angle_value":top_value,
        "label_to_sealer_value_1":bottom_value,
        "label_to_sealer_value_2":left_value,
    }
    mp = MongoHelper().getCollection('measurment_values')
    mp_data = mp.find_one()
    if mp_data is None:
        mp.insert_one(pay_load_data)
    else:
        mp.update({'_id' : mp_data['_id']}, {"$set" : pay_load_data})
    return pay_load_data, 200


def flag_util(data):
    message = data.get('message')
    is_flag = data.get('isFlagged')
    get_id = data.get('inspection_id')
    flag_details = {
        "flag_message":message,
        "is_flag": is_flag,
    }
    try:
        mp = MongoHelper().getCollection(str(get_id)+"_results")
        mp_data = mp.find_one()
        value = [i for i in mp.find().sort([( '_id', -1)]).limit(1)]
        _id_new = value[0]['_id']
        if mp_data is None:
            mp.insert_one(flag_details)
        else:
            mp.update({'_id' :ObjectId(_id_new)}, {"$set" : flag_details})
        image = CacheHelper().get_json('flag_input_frame')
        cv2.imwrite("save_flag_image/save_flag_image_"+str(_id_new)+".jpg", image)
        return "success",200  
    except Exception as e:
        print(e)
        return "Details not available", 400




