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
import os
import base64
import hashlib
import shutil
from copy import deepcopy

from ruamel import yaml

from fate_arch.common import file_utils
from fate_arch.protobuf.python import default_empty_fill_pb2

from fate_flow.protobuf.python.pipeline_pb2 import Pipeline
from fate_flow.model import serialize_buffer_object, parse_proto_object, Locker
from fate_flow.settings import stat_logger, TEMP_DIRECTORY


def local_cache_required(method):
    def magic(self, *args, **kwargs):
        if not self.exists():
            raise FileNotFoundError(f'Can not found {self.model_id} {self.model_version} model local cache')
        return method(self, *args, **kwargs)
    return magic


class PipelinedModel(Locker):
    def __init__(self, model_id, model_version):
        """
        Support operations on FATE PipelinedModels
        :param model_id: the model id stored at the local party.
        :param model_version: the model version.
        """
        self.model_id = model_id
        self.model_version = model_version
        self.model_path = file_utils.get_project_base_directory("model_local_cache", model_id, model_version)
        self.define_proto_path = os.path.join(self.model_path, "define", "proto")
        self.define_proto_generated_path = os.path.join(self.model_path, "define", "proto_generated_python")
        self.define_meta_path = os.path.join(self.model_path, "define", "define_meta.yaml")
        self.variables_index_path = os.path.join(self.model_path, "variables", "index")
        self.variables_data_path = os.path.join(self.model_path, "variables", "data")
        self.default_archive_format = "zip"
        self.pipeline_model_name = "Pipeline"
        self.pipeline_model_alias = "pipeline"
        super().__init__(self.model_path)

    def create_pipelined_model(self):
        if self.exists():
            raise FileExistsError("Model creation failed because it has already been created, model cache path is {}".
                                  format(self.model_path))
        os.makedirs(self.model_path)

        with self.lock:
            for path in [self.variables_index_path, self.variables_data_path]:
                os.makedirs(path)
            shutil.copytree(file_utils.get_python_base_directory("fate_flow", "protobuf", "proto"), self.define_proto_path)
            shutil.copytree(file_utils.get_python_base_directory("fate_flow", "protobuf", "python"), self.define_proto_generated_path)
            with open(self.define_meta_path, "x", encoding="utf-8") as fw:
                yaml.dump({"describe": "This is the model definition meta"}, fw, Dumper=yaml.RoundTripDumper)

    def save_component_model(self, component_name, component_module_name, model_alias, model_buffers, tracker_client=None):
        model_proto_index = {}
        component_model = {"buffer": {}}
        component_model_storage_path = os.path.join(self.variables_data_path, component_name, model_alias)
        if not tracker_client:
            os.makedirs(component_model_storage_path, exist_ok=True)
        for model_name, (proto_index, buffer_object_serialized_string) in model_buffers.items():
            storage_path = os.path.join(component_model_storage_path, model_name)
            # buffer_object_serialized_string = buffer_object.SerializeToString()
            # if not buffer_object_serialized_string:
            #     fill_message = default_empty_fill_pb2.DefaultEmptyFillMessage()
            #     fill_message.flag = 'set'
            #     buffer_object_serialized_string = fill_message.SerializeToString()
            if not tracker_client:
                with self.lock, open(storage_path, "wb") as fw:
                    fw.write(buffer_object_serialized_string)
            else:
                component_model["buffer"][storage_path.replace(file_utils.get_project_base_directory(), "")] = \
                    base64.b64encode(buffer_object_serialized_string).decode()
            model_proto_index[model_name] = proto_index  # index of model name and proto buffer class name
            stat_logger.info("Save {} {} {} buffer".format(component_name, model_alias, model_name))
        if not tracker_client:
            self.update_component_meta(component_name=component_name,
                                       component_module_name=component_module_name,
                                       model_alias=model_alias,
                                       model_proto_index=model_proto_index)
            stat_logger.info("Save {} {} successfully".format(component_name, model_alias))
        else:
            component_model["component_name"] = component_name
            component_model["component_module_name"] = component_module_name
            component_model["model_alias"] = model_alias
            component_model["model_proto_index"] = model_proto_index
            tracker_client.save_component_output_model(component_model)

    def write_component_model(self, component_model):
        for storage_path, buffer_object_serialized_string in component_model.get("buffer").items():
            storage_path = file_utils.get_project_base_directory()+storage_path
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            with open(storage_path, "wb") as fw:
                fw.write(base64.b64decode(buffer_object_serialized_string.encode()))
        self.update_component_meta(component_name=component_model["component_name"],
                                   component_module_name=component_model["component_module_name"],
                                   model_alias=component_model["model_alias"],
                                   model_proto_index=component_model["model_proto_index"])
        stat_logger.info("save {} {} successfully".format(component_model["component_name"],
                                                          component_model["model_alias"]))

    def read_component_model(self, component_name, model_alias, parse=True):
        component_model_storage_path = os.path.join(self.variables_data_path, component_name, model_alias)
        model_proto_index = self.get_model_proto_index(component_name=component_name,
                                                       model_alias=model_alias)
        model_buffers = {}
        for model_name, buffer_name in model_proto_index.items():
            with open(os.path.join(component_model_storage_path, model_name), "rb") as fr:
                buffer_object_serialized_string = fr.read()
                if parse:
                    model_buffers[model_name] = parse_proto_object(buffer_name=buffer_name,
                                                                   serialized_string=buffer_object_serialized_string)
                else:
                    model_buffers[model_name] = [buffer_name, base64.b64encode(buffer_object_serialized_string).decode()]
        return model_buffers

    def read_pipelined_model(self, component_name, parse=True):
        model_alias = self.pipeline_model_alias
        component_model_storage_path = os.path.join(self.variables_data_path, component_name, model_alias)
        model_proto_index = self.get_model_proto_index(component_name=component_name,
                                                       model_alias=model_alias)
        model_buffers = {}
        for model_name, buffer_name in model_proto_index.items():
            with open(os.path.join(component_model_storage_path, model_name), "rb") as fr:
                buffer_object_serialized_string = fr.read()
                if parse:
                    model_buffers[model_name] = parse_proto_object(buffer_name=buffer_name,
                                                                   serialized_string=buffer_object_serialized_string,
                                                                   buffer_object=Pipeline)
                else:
                    model_buffers[model_name] = [buffer_name, base64.b64encode(buffer_object_serialized_string).decode()]
        return model_buffers

    @local_cache_required
    def collect_models(self, in_bytes=False, b64encode=True):
        model_buffers = {}
        with open(self.define_meta_path, "r", encoding="utf-8") as fr:
            define_index = yaml.safe_load(fr)
        for component_name in define_index.get("model_proto", {}).keys():
            for model_alias, model_proto_index in define_index["model_proto"][component_name].items():
                component_model_storage_path = os.path.join(self.variables_data_path, component_name, model_alias)
                for model_name, buffer_name in model_proto_index.items():
                    with open(os.path.join(component_model_storage_path, model_name), "rb") as fr:
                        serialized_string = fr.read()
                    if not in_bytes:
                        model_buffers[model_name] = parse_proto_object(buffer_name, serialized_string)
                    else:
                        if b64encode:
                            serialized_string = base64.b64encode(serialized_string).decode()
                        model_buffers["{}.{}:{}".format(component_name, model_alias, model_name)] = serialized_string
        return model_buffers

    def exists(self):
        return os.path.exists(self.model_path)

    def save_protobuf(self, buffer_object, filepath):
        serialized_string = serialize_buffer_object(buffer_object)
        with self.lock, open(filepath, "wb") as fw:
            fw.write(serialized_string)
        return filepath

    def save_pipeline(self, buffer_object):
        return self.save_protobuf(buffer_object, os.path.join(self.model_path, "pipeline.pb"))

    @local_cache_required
    def packaging_model(self):
        archive_file_path = shutil.make_archive(base_name=self.archive_model_base_path, format=self.default_archive_format, root_dir=self.model_path)

        with open(archive_file_path, 'rb') as f:
            sha1 = hashlib.sha1(f.read()).hexdigest()
        with open(archive_file_path + '.sha1', 'w', encoding='utf8') as f:
            f.write(sha1)

        stat_logger.info("Make model {} {} archive on {} successfully. sha1: {}".format(
            self.model_id, self.model_version, archive_file_path, sha1))
        return archive_file_path

    def unpack_model(self, archive_file_path: str):
        if self.exists():
            raise FileExistsError("Model {} {} local cache already existed".format(self.model_id, self.model_version))

        if os.path.isfile(archive_file_path + '.sha1'):
            with open(archive_file_path + '.sha1', encoding='utf8') as f:
                sha1_orig = f.read().strip()
            with open(archive_file_path, 'rb') as f:
                sha1 = hashlib.sha1(f.read()).hexdigest()
            if sha1 != sha1_orig:
                raise ValueError('Hash not match. path: {} expected: {} actual: {}'.format(
                    archive_file_path, sha1_orig, sha1))

        os.makedirs(self.model_path)
        with self.lock:
            shutil.unpack_archive(archive_file_path, self.model_path)
        stat_logger.info("Unpack model archive to {}".format(self.model_path))

    @local_cache_required
    def update_component_meta(self, component_name, component_module_name, model_alias, model_proto_index):
        """
        update meta info yaml
        :param component_name:
        :param component_module_name:
        :param model_alias:
        :param model_proto_index:
        :return:
        """
        with self.lock, open(self.define_meta_path, "r+", encoding="utf-8") as f:
            _define_index = yaml.safe_load(f)
            if not isinstance(_define_index, dict):
                raise ValueError('Invalid meta file')
            define_index = deepcopy(_define_index)

            define_index["component_define"] = define_index.get("component_define", {})
            define_index["component_define"][component_name] = define_index["component_define"].get(component_name, {})
            define_index["component_define"][component_name].update({"module_name": component_module_name})
            define_index["model_proto"] = define_index.get("model_proto", {})
            define_index["model_proto"][component_name] = define_index["model_proto"].get(component_name, {})
            define_index["model_proto"][component_name][model_alias] = define_index["model_proto"][component_name].get(model_alias, {})
            define_index["model_proto"][component_name][model_alias].update(model_proto_index)

            if define_index != _define_index:
                f.seek(0)
                yaml.dump(define_index, f, Dumper=yaml.RoundTripDumper)
                f.truncate()

    @local_cache_required
    def get_model_proto_index(self, component_name, model_alias):
        with open(self.define_meta_path, "r", encoding="utf-8") as fr:
            define_index = yaml.safe_load(fr)
        return define_index.get("model_proto", {}).get(component_name, {}).get(model_alias, {})

    @local_cache_required
    def get_component_define(self, component_name=None):
        with open(self.define_meta_path, "r", encoding="utf-8") as fr:
            define_index = yaml.safe_load(fr)

        if component_name is not None:
            return define_index.get("component_define", {}).get(component_name, {})
        return define_index.get("component_define", {})

    @property
    def archive_model_base_path(self):
        return os.path.join(TEMP_DIRECTORY, "{}_{}".format(self.model_id, self.model_version))

    @property
    def archive_model_file_path(self):
        return "{}.{}".format(self.archive_model_base_path, self.default_archive_format)

    def calculate_model_file_size(self):
        size = 0
        for root, dirs, files in os.walk(self.model_path):
            size += sum([os.path.getsize(os.path.join(root, name)) for name in files])
        return round(size/1024)
