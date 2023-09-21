- 在FATE/fate.env中增加一个自定义的Provider的版本信息
- `FATE/fateflow/conf/component_registry.json` 需要添加Provider的信息
- `component_plugins`的目录结构：
```
.
|______init__.py
|____yunphant
| |______init__.py
| |____README.md
| |____components
| | |_____base.py
| | |______init__.py
| | |____components.py
```
> 目录结构中有 components/components.py 文件和 components/_base.py文件
- `FATE/fateflow/python/fate_flow/manager/provider_manager.py` 需要加入Provider注册的驱动代码
- 在`components`目录下放入自定义的component
- 在系统启动时会扫描`components`目录把组件信息写入到元数据库中
