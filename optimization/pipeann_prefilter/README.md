# PipeANN 预过滤路由优化

此目录包含已在原WSL实验环境验证的源码补丁、复现脚本和证据。优化只对查询路由增加选择率阈值：`FVS_PREFILTER_MAX_SELECTIVITY=0`保留原成本模型，`0.05`对估计选择率≤5%的查询选择已有预过滤路径。

2026年11月14日实测：Medium、L=40、7组配对测试中，延迟中位数4382.3→1904.6 μs，QPS 225.8→523.8，Recall@10 92.4%→95.8%。该结论仅对应当前数据、索引、硬件、缓存协议和参数；详细波动、内存代价及High结果见第五章正文。

## 当前已经完成的工作

- 独立源码位于WSL的 `/home/zhangyue/course/fvs-course-lab/systems/PipeANN_prefilter_verified`。
- 基于官方提交 `2ec84fe20c37dc3cc236b66f7eba31c0cc80bf1e`，只修改一个查询路由文件。
- Release、AIO、tcmalloc查询程序已编译成功。
- 7组×3负载×2策略，共42条正式记录；另保留6次预热。
- 本上传副本将每次运行的 command.json、filter_config.json、results.csv、run.log 保存于 `evidence/raw_logs.zip`；解压后恢复 `evidence/raw/`。
- `evidence/manifest.json` 记录实验配置、执行顺序、环境开关、源码补丁及二进制哈希。
- 原始报告对应的30条正式记录及环境文件保存在 `evidence/original_report/`；没有将其与新实验混作配对结果。

## 在当前机器重新测量

在WSL终端执行。以下命令使用已经编译好的独立源码，输出目录必须是一个尚不存在的新目录。

```bash
python3 /mnt/d/研究生材料/课程资料/计算机系统设计/实验一/fvs-course-lab-main/optimization/pipeann_prefilter/benchmark.py \
  --course-root /home/zhangyue/course/fvs-course-lab \
  --output /home/zhangyue/course/fvs-course-lab/course_runs/prefilter-repeat-01 \
  --pairs 7
```

不需要重新下载数据、重新构建索引或重跑两系统的全部正式实验。重测时保持宿主机负载相近，避免同时编译或运行其他性能测试。脚本不主动清空缓存，先对每种策略和负载各预热一次，再交替顺序测试。

## 在另一份课程仓库构建

先按照课程要求准备编译依赖、源码、数据和正式索引，再将本目录复制到课程仓库中。使用WSL/Linux的Python3与CMake运行以下命令。准备脚本会从本地PipeANN Git仓库克隆到独立目录，并检出固定提交；如果目标目录已存在会停止，防止覆盖现有修改。

```bash
python3 optimization/pipeann_prefilter/prepare.py \
  --course-root "$PWD" \
  --source "$PWD/systems/PipeANN" \
  --jobs 4

python3 optimization/pipeann_prefilter/benchmark.py \
  --course-root "$PWD" \
  --output "$PWD/course_runs/prefilter-verified-01" \
  --pairs 7
```

`prepare.py`只构建本次测试所需的 `search_disk_index_filtered`，不构建新的索引。默认阈值关闭。若仅需手动应用补丁，可在干净的课程固定PipeANN源码中运行：

```bash
git apply --check /absolute/path/prefilter_route.patch
git apply /absolute/path/prefilter_route.patch
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DIO_ENGINE=aio -DUSE_TCMALLOC=ON
cmake --build build --target search_disk_index_filtered -j 4
```

## 单独执行A或B

在课程仓库根目录运行，将run-id改成未使用的名称：

```bash
FVS_PREFILTER_MAX_SELECTIVITY=0.05 \
python3 adapters/pipeann_adapter.py search \
  --repo "$PWD/systems/PipeANN_prefilter_verified" \
  --dataset-root "$PWD/datasets/yfcc_course_v1" \
  --tier formal --run-root "$PWD/course_runs" \
  --bucket medium --L 40 --threads 1 --beamwidth 8 --k 10 --mem-L 0 \
  --run-id prefilter-manual-B-01
```

将环境变量设为0并使用不同run-id即可运行A。只更改环境变量即可回退策略。当前没有验证其他L、其他数据规模、其他数据分布及多标签合取负载，改变这些条件后应重新校准。

## 报告与代码发布

1. 先阅读 `报告检查与补充顺序.md`。
2. 将 `第五章_优化设计与实现.md` 的正文复制进报告，图像使用 `figures/medium_ab.png`；需要矢量图时使用同目录SVG。
3. 同步第六章中“尚未实现”的旧结论，并更新Word目录。
4. 将本目录或课程仓库的优化分支发布到自己的GitHub仓库，保留官方来源、固定版本及许可证。报告中填写真实仓库URL和提交SHA，推荐链接到该提交下的补丁、说明与结果文件。

报告中的代码链接应指向本仓库及实际提交；课程仓库或PipeANN官方仓库用于注明上游来源。

不要上传数据集、预构建索引、编译产物或原始第三方Git目录。`modified_source/LICENSE`保留官方PipeANN许可证，发布源码快照时一并保留；其余脚本和补丁足以复现修改。原始日志中包含本地路径，发布前可以做一致的路径脱敏，但应保持数值、命令参数及补丁内容不变。
