from common.utils import MongoHelper
from livis.settings import *
from bson import ObjectId
from plan.utils import get_todays_planned_production_util
from common.utils import GetLabelData
import json


###############################################PART CRUDS#####################################
def add_part_details_task(data):
    """
    {
    "part_number": "pt11",
    "part_description": "fjjff"
    }
    """
    try:
        print(data,'ffffffffffffffffffffffffffffffffffffffffffffffffff')
        part_name = data.get('part_name',None)
        print(part_name,'lllllllllllllllllllllllllllllllllllllllllllllllll')
        part_type = data.get('part_type',None)
        # kanban = data.get('kanban',None)
        features = data.get('features',None)
        defeats = data.get('defects',None)
        isdeleted = False
        mp = MongoHelper().getCollection("parts")
        collection_obj = {
            "select_model": part_name,
            "isdeleted" : isdeleted,
            "label_type": part_type,
            "features":features,
            "defeats":defeats
        }
        part_id = mp.insert_one(collection_obj)
        print(part_id)
        return part_id
    except Exception as e:
        return "Could not add part: "+str(e)


def delete_part_task(data):
    _id = data.get('part_name',None)
    print(_id,'ffffffffffffffff_iddddddddddddddddddddddddddddddddddddddd')
    mp = MongoHelper().getCollection("parts")
    p = mp.find_one({'_id' : ObjectId(_id)})
    if p:
        isdeleted = p.get('isdeleted')
        if not isdeleted:
            p['isdeleted'] = True
        mp.update({'_id' : p['_id']}, {'$set' :  p})
        return _id
    else:
        return "Part not found."


def update_part_task(data):
    """
    {
        "_id": "242798143hdw7q33913413we2",
        "part_number": "pt11",
        "part_description": "fjjff"
    }
    """
    _id = data.get('_id')
    if _id:
        mp = MongoHelper().getCollection("parts")
        pc = mp.find_one({'_id' : ObjectId(_id)})
        if pc:
            part_name = data.get('edit_part_name',None)
            part_type = data.get('edit_part_type',None)
            features = data.get('edit_defects',None)
            defects = data.get('edit_features',None)
            kanban = data.get('kanban',None)
            if part_name:
                pc['select_model'] = part_name
            if part_type:
                pc['label_type'] = part_type
            if part_type:
                pc['features'] = features
            if part_type:
                pc['defeats'] = defects			
            mp.update({'_id' : pc['_id']}, {'$set' :  pc})
        else:
            return "Part not found"
        return "Updated Successfully"
    else:
        return "Please enter the part ID."
        

def get_part_details_task(part_id):
    mp = MongoHelper().getCollection("parts")
    p = mp.find_one({'_id' : ObjectId(part_id)})
    if p:
        return p
    else:
        return {}

def get_all_part_details_task():
    mp = MongoHelper().getCollection("parts")
    print(mp,'mppppppppppp')
    parts =[p for p in  mp.find({'isdeleted' : False})]
    print(parts,'parts')
    for part in parts:
        part["part_id"] = str(part["_id"])
        part["part_name"] = str(part["select_model"])
    if parts:
        return parts
    else:
        return {}
      