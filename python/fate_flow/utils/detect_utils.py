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
import typing

# 用于http请求时,request.json中的字段的检查，检查是否包含了必要的字段
def check_config(config: typing.Dict, required_arguments: typing.List):
    if not config or not isinstance(config, dict):
        raise TypeError('no parameters')

    no_arguments = []
    error_arguments = []
    for require_argument in required_arguments:
        if isinstance(require_argument, tuple):  # 判断一下类型是否为元组，这个元组要求第0个元素是请求参数中的键，第1个元素为要求的值或值的集合（可以为元组或列表）
            config_value = config.get(require_argument[0], None)  # 如果为元组，则取出元组第0个元素作为请求参数中的键，获取请求参数中的值
            if isinstance(require_argument[1], (tuple, list)):  # 要求的值为一个集合（元组或列表）
                if config_value not in require_argument[1]:  # 判断对应的请求参数中值是否在要求的值的集合中
                    error_arguments.append(require_argument)  # 不在要求的值的集合中则算是参数错误，添加到error_arguments里面去
            elif config_value != require_argument[1]:  # 要求的参数不为集合，那就直接对比请求参数的值和要求的值
                error_arguments.append(require_argument)  # 否则值不符合要求，算是参数错误
        elif require_argument not in config:  # 要求的参数不为tuple的情况，就直接检查要求的参数在请求参数里面有没有
            no_arguments.append(require_argument)  # 如果必须的参数在请求参数里面不存在，则算是缺少参数的错误

    if no_arguments or error_arguments:
        error_string = ""
        if no_arguments:
            error_string += "required parameters are missing: {}; ".format(",".join(no_arguments))
        if error_arguments:
            error_string += "required parameter values: {}".format(",".join(["{}={}".format(a[0], a[1]) for a in error_arguments]))
        raise KeyError(error_string)
