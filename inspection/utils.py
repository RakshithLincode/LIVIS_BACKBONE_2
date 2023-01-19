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
		#print("kanban dict", kanban_dict)
		kanban_dict = json.loads(f.read())
		predicted_dict = self.list_to_dict()
		#print("predicted dict in check defects", predicted_dict)
		if len(predicted_dict)> 0:
			
				kanban_for_view_list = kanban_dict["view"+str(self.cam_view)]
				for item in kanban_for_view_list:
					for key, value in predicted_dict.items():
						if item.get("defect_name") == key:
							self.status = "Rejected"
							if key != self.part_name or key!="damler" or key!="scania" or key!="cum40":
								if key not in [self.part_name, "damler", "scania","cum40"]:
									[self.reject_reasons.append(key) for cnt in range(value)]
							
						#return 0
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
	# print("curr_insp_id.inserted_id",curr_insp_id.inserted_id)
	response = {"current_inspection_id":curr_insp_id.inserted_id, "part_name": part_name}
	return response,200


#API to save inspection from all cameras.
def save_inspection_per_view(data):
	####["feauture_name":"hole", "count":1,"coords":[]],
	inspection_id = data.get('inspection_id',None)
	camera_view = data.get('camera_view',None)
	part_name = data.get('part_name', None)
	topic = camera_view
	
	mp = MongoHelper().getCollection('inspection')
	doc = mp.find_one({'_id' : ObjectId(inspection_id)})
	part_name_from_db = str(doc["part_name"])
	part_id = str(doc["part_id"])
	current_part = CurrentPart(part_name=part_name_from_db, part_id=part_id)
	#current_part
	quick_report = {}
	raw_data = {}
	qr_code = ""
	## Check for part name
	print("part name received from worker ", part_name)
	if part_name != "" and part_name != part_name_from_db:
		current_part.status = "Rejected"
		current_part.reject_reasons.append("Part mismatch")
	predicted_list = get_data_feed(topic+'_predicted_list')
	print("predicted list from worker", predicted_list, " for topic", topic)

	

	current_part.cam_view = camera_view
	current_part.predictions_list = predicted_list
	quick_report["camera_view"] = current_part.cam_view
	current_part.check_defects()
	#if current_part.status == "Accepted":
	current_part.check_features()
	for i in current_part.reject_reasons:
		if current_part.defects_dict.get(i):
			current_part.defects_dict[i] +=1
		else:
			current_part.defects_dict[i] = 1
	quick_report["camera_index"] = topic
	quick_report['status'] = current_part.status
	if current_part.status == "Rejected":
		quick_report['reason'] = current_part.defects_dict
	else:
		quick_report['reason'] = {}
	
	ps = MongoHelper().getCollection(str(inspection_id))
	#print("-----------------Save inspection ID--------------------------",str(inspection_id))
	quick_report['time_stamp'] = str(datetime.datetime.now().replace(microsecond=0))
	quick_report["inspection_id"] = inspection_id
	quick_report['inference_image'] = None
	quick_report['remark'] = ""
	#quick_report['qr_code'] = qr_code

	imgs = get_single_frame(topic+'_predicted_frame')
	input_frame = get_single_frame(topic+'_input_frame')
	#print('**********************TOPIC:',topic,'\tImage Shape:',imgs.shape)
	import bson

	x = bson.objectid.ObjectId()

	fname = "/home/mim/Main/dataimages/images/" + str(x)+'.jpg'
	inp_frame = "/home/mim/Main/dataimages/images/input_frame_" + str(x)+'.jpg'

	cv2.imwrite(fname, imgs)
	cv2.imwrite(inp_frame,input_frame)
	#print("Writing imgae ,",fname, cv2.imwrite(fname, imgs))   ### need to debug
	quick_report['inference_image'] = "http://127.0.0.1:3306/images/" + str(x)+'.jpg'
	quick_report['input_image'] = "http://127.0.0.1:3306/images/input_frame_" + str(x)+'.jpg'

	quick_report['consolidated'] = False
	# if len(current_part.reject_reasons) > 0:
	#     quick_report["detect"]
	mongo_id = ps.insert_one(quick_report)
	quick_report['_id'] = str(quick_report['_id'])
	print("quick_report-----------------",quick_report)
	#print("Sub inspection ID", str(mongo_id.inserted_id))
	#CacheHelper().set_json({"detzo" : str(mongo_id.inserted_id)})
	return quick_report

def save_inspection(data):
	inspection_id = data.get('inspection_id', None)
	print(inspection_id,'jjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjj')
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

	#if len(docs) != 15:  ### for 15th view
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
		if key == "Part mismatch" or key =="21_hole_absence":  ################################***********
			value = 1
		results["reasons"][key] = value 

		# str_ = str(key)+" ("+str(value)+") "
		# results["reasons"].append(str_)
		# str_ = ""
	print(" ********* Results are*****************")
	print(results)
	
 


	mp = MongoHelper().getCollection(str(inspection_id)+"_results")
	mp.insert_one(results)
	return status
		
def get_data_feed(topic):
	#print("Topic : : ", topic)
	#topic= str(topic)+str("_predicted_list")
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
	inspection_id = ""
	response = {}
	if len(insp_coll) > 0:
		res = insp_coll[-1]
		response["inspection_id"] = str(res['_id'])
		response["part_name"] = res["part_name"]
		# print("*****************Running process inspection_id*********************",inspection_id)
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
	#inspection_id = data.get('inspection_id',None)

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
	mp = MongoHelper().getCollection( str(inspectionid) + '_results')
	dataset = [p for p in mp.find().sort( "$natural", -1 )]
	dataset1 = [p for p in mp.find({"status":"Accepted"})]
	dataset2 = [p for p in mp.find({"status":"Rejected"})]
	total_production = len(dataset)
	total_accepted_count = len(dataset1)
	total_rejected_count = len(dataset2)

	if len(dataset) > 0:
		dataset = dataset[0]
		#s = datetime.datetime.strptime(dataset.get('inference_start_time',""), '%Y-%m-%d %H:%M:%S')
		#e = datetime.datetime.strptime(dataset.get('inference_end_time',""), '%Y-%m-%d %H:%M:%S')
		#dataset['duration'] = str(e-s)
		dataset['total'] = str(total_production)
		dataset['total_accepted'] = str(total_accepted_count)
		dataset['total_rejected'] = str(total_rejected_count)
		if "None" in dataset['label_angle']:
			dataset['label_angle'] = []
		if None in dataset['label_to_sealent_measurment']:
			dataset['label_to_sealent_measurment'] = []
		# dataset['inference_urls'] = inference_urls
	else:
		part_name = CacheHelper().get_json('part_name')
		dataset = {'part_name':part_name}
	return dataset, 200 


# def get_defect_list(inspectionid):
#     total = 0
#     total_accepted = 0
#     total_rejected = 0
#     # response = {}
#     defect_list = []
#     mp = MongoHelper().getCollection(str(inspectionid)+"_results")
#     #print("==================================>",mp)
#     list_ = [i for i in mp.find()]

#     total = len(list_)
#     for item in list_:
#         # print(item,total)
#         if item["status"] == "Rejected":
#             total_rejected += 1
#             defect_list.append(item['defects'])
#             defect_list.append(item['ocr_barcode_mismatch'])
#         elif item["status"] == "Accepted":
#             total_accepted += 1

#     if len(list_) > 0:
#         doc = list_[-1]
#     else:
#         doc = {}
	
#     response = {"status":doc.get("status"), "total_count": total, "total_accepted": total_accepted,
#                 "total_rejected": total_rejected,
#                 "reasons":doc.get("reasons"),
#                 "defect_list":doc.get("defect_list"),
#                 "part_name":doc.get("part_name"),
#                 }


#     #print(response)
#     return response, 200


# mp = MongoHelper().getCollection( str(inspection_id) + '_log')
#     dataset = [p for p in mp.find().sort( "$natural", -1 )]
#     # print(" dataset is ",dataset)
#     # dataset1 = [p for p in mp.find({"isAccepted":True})]
#     # dataset2 = [p for p in mp.find({"isAccepted":False})]

#     dataset1 = [p for p in mp.find({"status":"Accepted"})]
#     dataset2 = [p for p in mp.find({"status":"Rejected"})]

	
#     total_production = len(dataset)
#     total_accepted_count = len(dataset1)
#     total_rejected_count = len(dataset2)

#     if len(dataset) > 0:
#         dataset = dataset[0]
#         #s = datetime.datetime.strptime(dataset.get('inference_start_time',""), '%Y-%m-%d %H:%M:%S')
#         #e = datetime.datetime.strptime(dataset.get('inference_end_time',""), '%Y-%m-%d %H:%M:%S')
#         #dataset['duration'] = str(e-s)
#         dataset['total'] = str(total_production)
#         dataset['total_accepted'] = str(total_accepted_count)
#         dataset['total_rejected'] = str(total_rejected_count)
#         #dataset['inference_urls'] = inference_urls
#     else:
#         part_name = CacheHelper().get_json('part_name')
#         dataset = {'part_name':part_name}
#     return dataset, 200
	


def get_inference_feed(cam_id):
	# cam_id = int(cam_id)
	# if cam_id < 11:  ## OCR frame
	print(cam_id)
	key = str(cam_id)
	while True:
		v = CacheHelper().get_json(key)
		im_b64_str = v
		ret, jpeg = cv2.imencode('.jpg', im_b64_str)
		frame = jpeg.tobytes()
	
		yield (b'--frame\r\n'
				b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
	



# def save_inspection_details_util(data):
#     inspection_id = data.get('current_inspection_id',None)
#     input_frame_path = data.get('input_frame',None)
#     mask_frame = data.get('mask_frame',None)
#     measure_frame = data.get('measure_frame',None)
#     inference_frame = data.get('inference_frame',None)
#     status = data.get('status',None)
	
	

#     inspection_details = {
#         "input_frame_path": input_frame_path,
#         "mask_frame":mask_frame,
#         "measure_frame":measure_frame,
#         "inference_frame":inference_frame,
#         "status":status        
#     }

#     print(inspection_details,'inspection_details')
#     try:
#         mp = MongoHelper().getCollection(str(inspection_id)+"_log")

#         ins = [i for i in mp.find().sort([( '$natural', -1)]).limit(1)][0]
#         print(ins,'inspectionsinspectionsinspectionsinspectionsinspectionsinspections')
#         mp.update_one({'_id':ObjectId(ins["_id"])},{'$set':inspection_details})

#         return "success",200
#     except Exception as e:
#         print(e)

#         return "Object not available", 400



# def get_metrics_util(inspection_id):
# 	"""
# 		Usage: Return the report of the the current inspection happening, that is stored in database. This information
# 			is used in the operator panel dashboard to convey to the user the current inspection process results.
# 		Request Parameters: {
# 							"inspection_id": "6224257708f3e625aa6b3b26"
# 							}
# 		Request Method: GET
# 		Response: {
# 					"part_id": "61d4257708f3e625aa6b3b26"
# 					"workstation_id": "6392257708f3e625aa6b3b26",
# 					"plan_id":plan_id,
# 					"start_time":createdAt,
# 					"end_time":"",
# 					"shift_id":shift_id,
# 					"operator_id":operator_id,
# 					"produced_on":current_date,
# 					"status":"started",
# 					"inference_urls" : ["url1","url2"],
# 					"duration":"",
# 					"total_accpeted":100,
# 					"total_rejected":10,
# 					"total":110
# 				}
# 		"""


# 	mp = MongoHelper().getCollection( str(inspection_id) + "_" + "log")
# 	dataset = [p for p in mp.find().sort( "$natural", -1 )]
# 	print(" dataset is ",dataset)
# 	# dataset1 = [p for p in mp.find({"isAccepted":True})]
# 	# dataset2 = [p for p in mp.find({"isAccepted":False})]

# 	dataset1 = [p for p in mp.find({"status":"Accepted"})]
# 	dataset2 = [p for p in mp.find({"status":"Rejected"})]
 
# 	total_production = len(dataset)
# 	total_accepted_count_left_frame_status = len(dataset1)
# 	total_rejected_count_left_frame_status = len(dataset2)
# 	current_part_name = CacheHelper().get_json("current_part_name")


# 	if len(dataset) > 0:
# 		dataset = dataset[0]

# 		dataset["part_name"] = current_part_name
# 		print("dataset-------------------",dataset)
# 		#s = datetime.datetime.strptime(dataset.get('inference_start_time',""), '%Y-%m-%d %H:%M:%S')
# 		#e = datetime.datetime.strptime(dataset.get('inference_end_time',""), '%Y-%m-%d %H:%M:%S')
# 		#dataset['duration'] = str(e-s)
# 		dataset['total'] = str(total_production)
# 		dataset['total_accepted_count_left_frame_status'] = str(total_accepted_count_left_frame_status)
# 		dataset['total_rejected_count_left_frame_status'] = str(total_rejected_count_left_frame_status)
# 		# dataset['total_accepted_count_right_frame_status'] = str(total_accepted_count_right_frame_status)
# 		# dataset['total_rejected_count_right_frame_status'] = str(total_rejected_count_right_frame_status)
# 		#dataset['inference_urls'] = inference_urls
# 	else:
# 		dataset = {}
# 	return dataset, 200


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
	# print(" dataset is ",dataset)
	# dataset1 = [p for p in mp.find({"isAccepted":True})]
	# dataset2 = [p for p in mp.find({"isAccepted":False})]

	dataset1 = [p for p in mp.find({"status":"Accepted"})]
	dataset2 = [p for p in mp.find({"status":"Rejected"})]

	
	total_production = len(dataset)
	total_accepted_count = len(dataset1)
	total_rejected_count = len(dataset2)

	if len(dataset) > 0:
		dataset = dataset[0]
		#s = datetime.datetime.strptime(dataset.get('inference_start_time',""), '%Y-%m-%d %H:%M:%S')
		#e = datetime.datetime.strptime(dataset.get('inference_end_time',""), '%Y-%m-%d %H:%M:%S')
		#dataset['duration'] = str(e-s)
		dataset['total'] = str(total_production)
		dataset['total_accepted'] = str(total_accepted_count)
		dataset['total_rejected'] = str(total_rejected_count)
		#dataset['inference_urls'] = inference_urls
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
	print(part_name,'part_namevvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv')
	print(inspection_id,'inspection_idvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv')
	mp = MongoHelper().getCollection(str(inspection_id)+"_results")

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
	}

	print(inspection_details,'inspection_details')
	try:
		mp = MongoHelper().getCollection(str(inspection_id)+"_results")

		_id = mp.insert_one(inspection_details)
		CacheHelper.set_json({"_id_new":mp.inserted_id})
		return "success",200
	except Exception as e:
		print(e)

		return "Object not available", 400

def start_inspection_util(data):
	inspection_id = data.get("inspection_id",None)
	part_name = data.get("part_name",None)
	

	# mp = MongoHelper().getCollection(str(inspection_id)+"_log")

	

	# inspection_details = {
	#     "inspection_id":inspection_id,
	#     "input_frames": "",
	#     "inference_frames":"",
	#     # "mask_image_path":mask_image_path,
	#     # "overall_result_path":overall_result_path,
	#     "status":"",
	#     "defect_list":"",
	#     "reject_reason":{"features":[], "defects":[]},
	#     "feature_list": [],
	#     "created_at":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
	#     "part_name": part_name
	# }

		
	try:
		# _id = mp.insert_one(inspection_details)
		# print(_id,'instred id')
		message = "Inspection starts"

		CacheHelper().set_json({"inspection_trigger":True})
		status_code = 200
	except:
		message = "Inspection is not started"
		status_code = 403

	return message,status_code
# def start_inspection_util(data):
# 	inspection_id = data.get("inspection_id",None)
# 	part_name =  CacheHelper().get_json('current_part_name')
# 	print(part_name,'part_namevvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv')
# 	print(inspection_id,'inspection_idvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv')

# 	mp = MongoHelper().getCollection(str("626fc2a37e544fd74356acf1")+"_results")

# 	inspection_details = {
# 		"created_at":datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
# 		'time_stamp': str(datetime.datetime.now().replace(microsecond=0)),
# 		"part_name": part_name,
# 	}
# 	try:
# 		_id = mp.insert_one(inspection_details)
# 		message = "Inspection starts"
# 		CacheHelper().set_json({"inspection_trigger":True})
# 		status_code = 200
# 	except:
# 		message = "Inspection is not started"
# 		status_code = 403

# 	return message,status_code


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




