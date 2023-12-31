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
from uuid import uuid1
from pathlib import Path

from flask import request

from fate_flow.entity.run_status import StatusSet
from fate_flow.entity import JobConfigurationBase
from fate_arch import storage
from fate_arch.common import FederatedMode
from fate_arch.common.base_utils import json_loads
from fate_flow.settings import UPLOAD_DATA_FROM_CLIENT
from fate_flow.utils.api_utils import get_json_result, error_response
from fate_flow.utils import detect_utils, job_utils
from fate_flow.scheduler.dag_scheduler import DAGScheduler
from fate_flow.operation.job_saver import JobSaver

page_name = 'data'


@manager.route('/<access_module>', methods=['post'])
def download_upload(access_module):
    job_id = job_utils.generate_job_id()

    if access_module == "upload" and UPLOAD_DATA_FROM_CLIENT and not (
            request.json and request.json.get("use_local_data") == 0):  # 默认1，代表使用client机器的数据;0代表使用fate flow服务所在机器的数据
        file = request.files['file']
        filename = Path(job_utils.get_job_directory(job_id), 'fate_upload_tmp', uuid1().hex)
        filename.parent.mkdir(parents=True, exist_ok=True)

        try:
            file.save(str(filename))  # 把接收到的文件存放到服务器本地的一个目录中
        except Exception as e:
            try:
                filename.unlink()
            except FileNotFoundError:
                pass

            return error_response(500, f'Save file error: {e}')

        job_config = request.args.to_dict() or request.form.to_dict()
        if "namespace" not in job_config or "table_name" not in job_config:
            # higher than version 1.5.1, support eggroll run parameters
            job_config = json_loads(list(job_config.keys())[0])

        job_config['file'] = str(filename)  # 上传数据配置文件中file参数的值设置为数据文件在服务器本地的路径
    else:  # 数据不由客户端上传，使用fate flow所在机器的数据, 路径还是配置文件中file这个参数批定
        job_config = request.json

    required_arguments = ['namespace', 'table_name']
    if access_module == 'upload':
        required_arguments.extend(['file', 'head', 'partition'])
    elif access_module == 'download':
        required_arguments.extend(['output_path'])
    elif access_module == 'writer':
        pass
    else:
        return error_response(400, f'Cannot support this operating: {access_module}')

    detect_utils.check_config(job_config, required_arguments=required_arguments)
    data = {}
    # compatibility
    if "table_name" in job_config:
        job_config["name"] = job_config["table_name"]
    for _ in ["head", "partition", "drop", "extend_sid", "auto_increasing_sid"]:
        if _ in job_config:
            if _ == "false":
                job_config[_] = False
            elif _ == "true":
                job_config[_] = True
            else:
                job_config[_] = int(job_config[_])
    if access_module == "upload":
        if int(job_config.get('drop', 0)) > 0:
            job_config["destroy"] = True
        else:
            job_config["destroy"] = False
        data['table_name'] = job_config["table_name"]
        data['namespace'] = job_config["namespace"]
        # 这里使用job_config中的table_name和namespace在数据库中t_storage_table_meta表中查询数据是否已存在
        data_table_meta = storage.StorageTableMeta(name=job_config["table_name"], namespace=job_config["namespace"])
        if data_table_meta and not job_config["destroy"]:  # 如果已存在且请求中drop参数为0，则直接返回数据表已存在
            return get_json_result(retcode=100,
                                   retmsg='The data table already exists.'
                                          'If you still want to continue uploading, please add the parameter --drop')
    # 生成根据job_conf生成job_dsl和job_runtime_conf
    job_dsl, job_runtime_conf = gen_data_access_job_config(job_config, access_module)
    # 根据job_dsl和job_runtime_conf提交这个job
    submit_result = DAGScheduler.submit(JobConfigurationBase(**{'dsl': job_dsl, 'runtime_conf': job_runtime_conf}),
                                        job_id=job_id)
    data.update(submit_result)
    return get_json_result(job_id=job_id, data=data)


@manager.route('/upload/history', methods=['POST'])
def upload_history():
    request_data = request.json
    if request_data.get('job_id'):
        tasks = JobSaver.query_task(component_name='upload_0', status=StatusSet.SUCCESS,
                                    job_id=request_data.get('job_id'), run_on_this_party=True)
    else:
        tasks = JobSaver.query_task(component_name='upload_0', status=StatusSet.SUCCESS, run_on_this_party=True)
    limit = request_data.get('limit')
    if not limit:
        tasks = tasks[-1::-1]
    else:
        tasks = tasks[-1:-limit - 1:-1]
    jobs_run_conf = job_utils.get_upload_job_configuration_summary(upload_tasks=tasks)
    data = get_upload_info(jobs_run_conf=jobs_run_conf)
    return get_json_result(retcode=0, retmsg='success', data=data)


def get_upload_info(jobs_run_conf):
    data = []

    for job_id, job_run_conf in jobs_run_conf.items():
        info = {}
        table_name = job_run_conf["name"]
        namespace = job_run_conf["namespace"]
        table_meta = storage.StorageTableMeta(name=table_name, namespace=namespace)
        if table_meta:
            partition = job_run_conf["partition"]
            info["upload_info"] = {
                "table_name": table_name,
                "namespace": namespace,
                "partition": partition,
                'upload_count': table_meta.get_count()
            }
            info["notes"] = job_run_conf["notes"]
            info["schema"] = table_meta.get_schema()
            data.append({job_id: info})
    return data


def gen_data_access_job_config(config_data, access_module):
    job_runtime_conf = {
        "initiator": {},
        "job_parameters": {"common": {}},
        "role": {},
        "component_parameters": {"role": {"local": {"0": {}}}}
    }
    initiator_role = "local"
    initiator_party_id = config_data.get('party_id', 0)
    job_runtime_conf["initiator"]["role"] = initiator_role
    job_runtime_conf["initiator"]["party_id"] = initiator_party_id
    job_parameters_fields = {"task_cores", "eggroll_run", "spark_run", "computing_engine", "storage_engine",
                             "federation_engine"}
    for _ in job_parameters_fields:
        if _ in config_data:
            job_runtime_conf["job_parameters"]["common"][_] = config_data[_]
    job_runtime_conf["job_parameters"]["common"]["federated_mode"] = FederatedMode.SINGLE
    job_runtime_conf["role"][initiator_role] = [initiator_party_id]
    job_dsl = {
        "components": {}
    }

    if access_module == 'upload':
        parameters = {
            "head",
            "partition",
            "file",
            "namespace",
            "name",
            "id_delimiter",
            "storage_engine",
            "storage_address",
            "destroy",
            "extend_sid",
            "auto_increasing_sid",
            "block_size",
            "schema",
            "with_meta",
            "meta"
        }
        update_config(job_runtime_conf, job_dsl, initiator_role, parameters, access_module, config_data)

    if access_module == 'download':
        parameters = {
            "delimiter",
            "output_path",
            "namespace",
            "name"
        }
        update_config(job_runtime_conf, job_dsl, initiator_role, parameters, access_module, config_data)

    if access_module == 'writer':
        parameters = {
            "namespace",
            "name",
            "storage_engine",
            "address",
            "output_namespace",
            "output_name"
        }
        update_config(job_runtime_conf, job_dsl, initiator_role, parameters, access_module, config_data)
    return job_dsl, job_runtime_conf


def update_config(job_runtime_conf, job_dsl, initiator_role, parameters, access_module, config_data):
    job_runtime_conf["component_parameters"]['role'][initiator_role]["0"][f"{access_module}_0"] = {}
    for p in parameters:
        if p in config_data:
            job_runtime_conf["component_parameters"]['role'][initiator_role]["0"][f"{access_module}_0"][p] = \
            config_data[p]
    job_runtime_conf['dsl_version'] = 2
    job_dsl["components"][f"{access_module}_0"] = {
        "module": access_module.capitalize()
    }
