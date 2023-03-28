import requests
import json
part_name = 'M3'
inspection_id = '64227d3c39770fd42d180832'
data = {'inspection_id':str(inspection_id),'part_name':str(part_name)}
data = json.dumps(data)
requests.post(url = 'http://localhost:8000/livis/v1/inspection/get_ui_trigger/', data = data)