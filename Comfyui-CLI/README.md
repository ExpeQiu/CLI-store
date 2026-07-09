# Comfyui-CLI

完全封装 ComfyUI 的 CLI 工具，支持图片生成、视频生成、数字人，并可配置装载的工作流。

## 快速开始

```bash
./setup.sh
./verify.sh

# 查看工作流
comfyui workflow list
comfyui workflow inspect wan2.1_txt2img

# 文生图
comfyui image t2i -t "白底红苹果产品摄影" --profile fast -o ./outputs

# 文生视频
comfyui video t2v -t "无人机航拍城市夜景" -o ./outputs

# 图生视频
comfyui video i2v --input ./keyframe.png -t "缓慢推进镜头" -o ./outputs

# 通用执行（覆盖 inject 参数）
comfyui run wan2.1_txt2img --prompt "红苹果" -p width=512 -p steps=10

# 配置
comfyui config show
comfyui config set capabilities.image.t2i flux_txt2img --save
```

## 工作流配置

- 内置工作流：`workflows/image|video|digital/`
- 用户覆盖：`data/workflows/`（优先级更高）
- 能力绑定：`config.yaml` → `capabilities.image.t2i` 等

```bash
comfyui workflow add ./my_workflow.json --name my_t2i --category image
comfyui config set capabilities.image.t2i my_t2i --save
```

## 数字人

数字人工作流默认走 RunningHub 云端，需配置：

```bash
export RUNNINGHUB_API_KEY=your_key
comfyui config set providers.runninghub.enabled true --save
comfyui digital run --portrait ./face.jpg --audio ./speech.mp3 -o ./outputs
```

## 目录结构

```
comfyui/          # Python 包
workflows/        # 内置工作流
data/workflows/   # 用户自定义
config.yaml       # 运行时配置
outputs/          # 默认输出
```
