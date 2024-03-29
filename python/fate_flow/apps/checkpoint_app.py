#
#  Copyright 2021 The FATE Authors. All Rights Reserved.
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
from flask import request, abort

from fate_flow.model.checkpoint import CheckpointManager
from fate_flow.utils.api_utils import error_response, get_json_result
from fate_flow.utils.detect_utils import check_config


def load_checkpoints():
    required_args = ['role', 'party_id', 'model_id', 'model_version', 'component_name']
    try:
        check_config(request.json, required_args)
    except Exception as e:
        abort(error_response(400, str(e)))
    # 下面一句的传参有点特色：** 表示取出字典中的键值对作为参数，这个i代表reuired_args中的元素，然后i的值作字典的键，值为request.json[i]
    checkpoint_manager = CheckpointManager(**{i: request.json[i] for i in required_args})
    checkpoint_manager.load_checkpoints_from_disk()
    return checkpoint_manager


@manager.route('/list', methods=['POST'])
def list_checkpoints():  # 加载checkpoint列表
    checkpoint_manager = load_checkpoints()
    return get_json_result(data=checkpoint_manager.to_dict())


@manager.route('/get', methods=['POST'])
def get_checkpoint():  # 根据 step_index 或 step_name 获取 checkpoint
    checkpoint_manager = load_checkpoints()

    if 'step_index' in request.json:
        try:
            request.json['step_index'] = int(request.json['step_index'])
        except Exception:
            return error_response(400, "Invalid 'step_index'")

        checkpoint = checkpoint_manager.get_checkpoint_by_index(request.json['step_index'])
    elif 'step_name' in request.json:
        checkpoint = checkpoint_manager.get_checkpoint_by_name(request.json['step_name'])
    else:
        return error_response(400, "'step_index' or 'step_name' is required")

    if checkpoint is None:
        return error_response(404, "The checkpoint was not found.")

    return get_json_result(data=checkpoint.to_dict(True))
