#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
from flask import request

from fate_arch.common.base_utils import deserialize_b64

from fate_flow.model.sync_model import SyncComponent
from fate_flow.operation.job_tracker import Tracker
from fate_flow.pipelined_model.pipelined_model import PipelinedModel
from fate_flow.pipelined_model.pipelined_component import PipelinedComponent
from fate_flow.settings import ENABLE_MODEL_STORE
from fate_flow.utils.api_utils import get_json_result, validate_request
from fate_flow.utils.model_utils import gen_party_model_id


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/metric_data/save',
               methods=['POST'])
def save_metric_data(job_id, component_name, task_version, task_id, role, party_id):
    request_data = request.json
    tracker = Tracker(job_id=job_id, component_name=component_name, task_id=task_id, task_version=task_version,
                      role=role, party_id=party_id)
    metrics = [deserialize_b64(metric) for metric in request_data['metrics']]
    tracker.save_metric_data(metric_namespace=request_data['metric_namespace'], metric_name=request_data['metric_name'],
                             metrics=metrics, job_level=request_data['job_level'])
    return get_json_result()


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/metric_meta/save',
               methods=['POST'])
def save_metric_meta(job_id, component_name, task_version, task_id, role, party_id):
    request_data = request.json
    tracker = Tracker(job_id=job_id, component_name=component_name, task_id=task_id, task_version=task_version,
                      role=role, party_id=party_id)
    metric_meta = deserialize_b64(request_data['metric_meta'])
    tracker.save_metric_meta(metric_namespace=request_data['metric_namespace'], metric_name=request_data['metric_name'],
                             metric_meta=metric_meta, job_level=request_data['job_level'])
    return get_json_result()


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/table_meta/create',
               methods=['POST'])
def create_table_meta(job_id, component_name, task_version, task_id, role, party_id):
    request_data = request.json
    tracker = Tracker(job_id=job_id, component_name=component_name, task_id=task_id, task_version=task_version,
                      role=role, party_id=party_id)
    tracker.save_table_meta(request_data)
    return get_json_result()


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/table_meta/get',
               methods=['POST'])
def get_table_meta(job_id, component_name, task_version, task_id, role, party_id):
    request_data = request.json
    tracker = Tracker(job_id=job_id, component_name=component_name, task_id=task_id, task_version=task_version,
                      role=role, party_id=party_id)
    table_meta_dict = tracker.get_table_meta(request_data)
    return get_json_result(data=table_meta_dict)


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/model/save',
               methods=['POST'])
@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/component_model/save',
               methods=['POST'])
@validate_request('model_id', 'model_version', 'component_model')  # 存储模型
def save_component_model(job_id, component_name, task_version, task_id, role, party_id):
    party_model_id = gen_party_model_id(request.json['model_id'], role, party_id)
    model_version = request.json['model_version']

    pipelined_model = PipelinedModel(party_model_id, model_version)
    pipelined_model.write_component_model(request.json['component_model'])

    if ENABLE_MODEL_STORE:  # 是否启用远程存储
        sync_component = SyncComponent(
            party_model_id=party_model_id,
            model_version=model_version,
            component_name=component_name,
        )
        # no need to test sync_component.remote_exists()
        sync_component.upload()  # 上传到远程存储

    return get_json_result()


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/model/get',
               methods=['POST'])
@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/component_model/get',
               methods=['POST'])
@validate_request('model_id', 'model_version', 'search_model_alias')
def get_component_model(job_id, component_name, task_version, task_id, role, party_id):
    party_model_id = gen_party_model_id(request.json['model_id'], role, party_id)
    model_version = request.json['model_version']

    if ENABLE_MODEL_STORE:
        sync_component = SyncComponent(
            party_model_id=party_model_id,
            model_version=model_version,
            component_name=component_name,
        )
        if not sync_component.local_exists() and sync_component.remote_exists():
            sync_component.download()

    pipelined_model = PipelinedModel(party_model_id, model_version)
    data = pipelined_model.read_component_model(component_name, request.json['search_model_alias'], False)

    return get_json_result(data=data)


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/model/run_parameters/get',
               methods=['POST'])
@validate_request('model_id', 'model_version')
def get_component_model_run_parameters(job_id, component_name, task_version, task_id, role, party_id):
    pipelined_component = PipelinedComponent(
        role=role,
        party_id=party_id,
        model_id=request.json['model_id'],
        model_version=request.json['model_version'],
    )
    data = pipelined_component.get_run_parameters()

    return get_json_result(data=data)


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/output_data_info/save',
               methods=['POST'])
def save_output_data_info(job_id, component_name, task_version, task_id, role, party_id):
    request_data = request.json
    tracker = Tracker(job_id=job_id, component_name=component_name, task_id=task_id, task_version=task_version,
                      role=role, party_id=party_id)
    tracker.insert_output_data_info_into_db(data_name=request_data["data_name"],
                                            table_namespace=request_data["table_namespace"],
                                            table_name=request_data["table_name"])
    return get_json_result()


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/output_data_info/read',
               methods=['POST'])
def read_output_data_info(job_id, component_name, task_version, task_id, role, party_id):
    request_data = request.json
    tracker = Tracker(job_id=job_id, component_name=component_name, task_id=task_id, task_version=task_version,
                      role=role, party_id=party_id)
    output_data_infos = tracker.read_output_data_info_from_db(data_name=request_data["data_name"])
    response_data = []
    for output_data_info in output_data_infos:
        response_data.append(output_data_info.to_human_model_dict())
    return get_json_result(data=response_data)


@manager.route('/<job_id>/<component_name>/<task_id>/<task_version>/<role>/<party_id>/summary/save',
               methods=['POST'])
def save_component_summary(job_id: str, component_name: str, task_version: int, task_id: str, role: str, party_id: int):
    request_data = request.json
    tracker = Tracker(job_id=job_id, component_name=component_name, task_id=task_id, task_version=task_version,
                      role=role, party_id=party_id)
    summary_data = request_data['summary']
    tracker.insert_summary_into_db(summary_data)
    return get_json_result()


@manager.route('/<job_id>/<component_name>/<role>/<party_id>/output/table', methods=['POST'])
def component_output_data_table(job_id, component_name, role, party_id):
    output_data_infos = Tracker.query_output_data_infos(job_id=job_id, component_name=component_name, role=role, party_id=party_id)
    if output_data_infos:
        return get_json_result(retcode=0, retmsg='success', data=[{'table_name': output_data_info.f_table_name,
                                                                  'table_namespace': output_data_info.f_table_namespace,
                                                                   "data_name": output_data_info.f_data_name
                                                                   } for output_data_info in output_data_infos])
    else:
        return get_json_result(retcode=100, retmsg='No found table, please check if the parameters are correct')
