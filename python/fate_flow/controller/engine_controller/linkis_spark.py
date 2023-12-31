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
from copy import deepcopy

import requests

from fate_flow.utils.log_utils import schedule_logger
from fate_flow.controller.engine_controller.engine import EngineABC
from fate_flow.db.runtime_config import RuntimeConfig
from fate_flow.entity.types import KillProcessRetCode
from fate_flow.entity.run_status import LinkisJobStatus
from fate_flow.settings import LINKIS_EXECUTE_ENTRANCE, LINKIS_SUBMIT_PARAMS, LINKIS_RUNTYPE, \
    LINKIS_LABELS, LINKIS_QUERT_STATUS, LINKIS_KILL_ENTRANCE, detect_logger
from fate_flow.db.service_registry import ServerRegistry
from fate_flow.db.db_models import Task


class LinkisSparkEngine(EngineABC):
    def run(self, task: Task, run_parameters, run_parameters_path, config_dir, log_dir, cwd_dir, **kwargs):
        linkis_execute_url = "http://{}:{}{}".format(ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("host"),
                                                     ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("port"),
                                                     LINKIS_EXECUTE_ENTRANCE)
        headers = {"Token-Code": ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("token_code"),
                   "Token-User": kwargs.get("user_name"),  # 这个是传进去的？为啥不是配在配置文件中？
                   "Content-Type": "application/json"}
        schedule_logger(Task.f_job_id).info(f"headers:{headers}")
        python_path = ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("python_path")
        execution_code = 'import sys\nsys.path.append("{}")\n' \
                         'from fate_flow.worker.task_executor import TaskExecutor\n' \
                         'task_info = TaskExecutor.run_task(job_id="{}",component_name="{}",' \
                         'task_id="{}",task_version={},role="{}",party_id={},' \
                         'run_ip="{}",config="{}",job_server="{}")\n' \
                         'TaskExecutor.report_task_update_to_driver(task_info=task_info)'. \
            format(python_path, task.f_job_id, task.f_component_name, task.f_task_id, task.f_task_version, task.f_role, task.f_party_id, RuntimeConfig.JOB_SERVER_HOST,
                   run_parameters_path, '{}:{}'.format(RuntimeConfig.JOB_SERVER_HOST, RuntimeConfig.HTTP_PORT))
        schedule_logger(task.f_job_id).info(f"execution code:{execution_code}")
        params = deepcopy(LINKIS_SUBMIT_PARAMS)
        schedule_logger(task.f_job_id).info(f"spark run parameters:{run_parameters.spark_run}")
        for spark_key, v in run_parameters.spark_run.items():
            if spark_key in ["spark.executor.memory", "spark.driver.memory", "spark.executor.instances",
                             "wds.linkis.rm.yarnqueue"]:
                params["configuration"]["startup"][spark_key] = v
        data = {
            "method": LINKIS_EXECUTE_ENTRANCE,
            "params": params,
            "executeApplicationName": "spark",
            "executionCode": execution_code,
            "runType": LINKIS_RUNTYPE,
            "source": {},
            "labels": LINKIS_LABELS
        }
        schedule_logger(task.f_job_id).info(f'submit linkis spark, data:{data}')
        task_info = {
            "engine_conf": {}
        }
        task_info["engine_conf"]["data"] = data
        task_info["engine_conf"]["headers"] = headers
        # 提交计算任务到linkis
        res = requests.post(url=linkis_execute_url, headers=headers, json=data)
        schedule_logger(task.f_job_id).info(f"start linkis spark task: {res.text}")
        if res.status_code == 200:
            if res.json().get("status"):
                raise Exception(f"submit linkis spark failed: {res.json()}")
            task_info["engine_conf"]["execID"] = res.json().get("data").get("execID")
            task_info["engine_conf"]["taskID"] = res.json().get("data").get("taskID")
            schedule_logger(task.f_job_id).info('submit linkis spark success')
        else:
            raise Exception(f"submit linkis spark failed: {res.text}")
        return task_info

    @staticmethod
    def kill(task):
        linkis_query_url = "http://{}:{}{}".format(ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("host"),
                                                   ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("port"),
                                                   LINKIS_QUERT_STATUS.replace("execID",
                                                                               task.f_engine_conf.get("execID")))
        headers = task.f_engine_conf.get("headers")
        response = requests.get(linkis_query_url, headers=headers).json()
        schedule_logger(task.f_job_id).info(f"querty task response:{response}")
        if response.get("data").get("status") != LinkisJobStatus.SUCCESS:
            linkis_execute_url = "http://{}:{}{}".format(ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("host"),
                                                         ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("port"),
                                                         LINKIS_KILL_ENTRANCE.replace("execID",
                                                                                      task.f_engine_conf.get("execID")))
            schedule_logger(task.f_job_id).info(f"start stop task:{linkis_execute_url}")
            schedule_logger(task.f_job_id).info(f"headers: {headers}")
            kill_result = requests.get(linkis_execute_url, headers=headers)
            schedule_logger(task.f_job_id).info(f"kill result:{kill_result}")
            if kill_result.status_code == 200:
                pass
        return KillProcessRetCode.KILLED

    def is_alive(self, task):
        process_exist = True
        try:
            linkis_query_url = "http://{}:{}{}".format(ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("host"),
                                                       ServerRegistry.FATE_ON_SPARK.get("linkis_spark", {}).get("port"),
                                                       LINKIS_QUERT_STATUS.replace("execID", task.f_engine_conf.get("execID")))
            headers = task.f_engine_conf["headers"]
            response = requests.get(linkis_query_url, headers=headers).json()
            detect_logger.info(response)
            if response.get("data").get("status") == LinkisJobStatus.FAILED:
                process_exist = False
        except Exception as e:
            detect_logger.exception(e)
            process_exist = False
        return process_exist
