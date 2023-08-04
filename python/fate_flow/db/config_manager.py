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
from .runtime_config import RuntimeConfig
from .service_registry import ServerRegistry
from .job_default_config import JobDefaultConfig
from fate_flow.manager.resource_manager import ResourceManager


class ConfigManager:
    @classmethod
    def load(cls):
        configs = {
            # job的默认配置
            "job_default_config": JobDefaultConfig.load(),
            # 从service_config.yaml和数据库表中加载配置信息，数据库中的信息是通过 FATE/fateflow/python/fate_flow/apps/service_app.py 的接口写入进去的
            "server_registry": ServerRegistry.load(),
        }
        ResourceManager.initialize()  # 引擎相关配置加载以及写入到数据表t_engine_registry
        RuntimeConfig.load_config_manager()  # 设置 LOAD_CONFIG_MANAGER = TRUE，仅此而已
        return configs