# 本地中文 ASR / FunASR 经验

## 适用场景

本页记录本机中文长录音转写的实际经验，尤其是 FunASR、Fun-ASR-Nano、Paraformer + VAD + Punc + CAM++、SenseVoiceSmall、Whisper turbo 在 CPU 环境下的取舍。

当前测试机器是 WSL2 CPU only，无可用 NVIDIA GPU，约 120 vCPU / 472 GiB RAM。Python 环境按本机约定优先用 `uv`。测试音频为 3:13:25 的中文课程录音：`（曹军武）国有企业“十五五”规划20251126.mp3`

工作目录：

```text
/home/timidly/funasr-cpu-demo
```

## 已测结论

| 方案 | 文本质量 | 时间戳 | 说话人 | CPU 速度 | 结论 |
|---|---|---:|---:|---:|---|
| Fun-ASR-Nano 60s 分块 | 当前最好 | 只有块级粗时间 | 无 | 8 路并行约 15-16 分钟 | 主稿首选 |
| Fun-ASR-Nano 2min 分块 | 局部复读 | 只有块级粗时间 | 无 | 较快 | 不作为最终稿 |
| Fun-ASR-Nano 5min 分块 | 严重复读/幻觉 | 只有块级粗时间 | 无 | 较快 | 不可用 |
| Paraformer + FSMN-VAD + CT-Punc + CAM++ | 粗字幕级，错字较多 | 句级 | 本录音不可靠 | 全量约 12:07 | 只当时间轴骨架 |
| SenseVoiceSmall | 速度快，但有数字混写和情绪 emoji | 无或不适合作此流程 | 无 | 全量约 6:24 | 不如 Nano，适合作候选对照 |
| Whisper turbo | 60 秒样本质量尚可 | 自带段时间 | 无 | 60 秒样本约 2 分半 | CPU 上太慢，不适合全量 |

主结论：

- 要中文纯文本主稿：优先 `Fun-ASR-Nano`，但必须控制切块长度。
- 要句级 timestamp：用 `Paraformer + FSMN-VAD + CT-Punc + CAM++`，再把 Nano 文本作为主稿对齐过去。
- 本录音是单人授课为主，CAM++ 把相邻短句频繁切成 `SPK0/SPK1`，speaker diarization 不可信。
- SenseVoiceSmall 很快，但本录音里出现 `十5`、`1个十5五`、情绪 emoji、数字混写，主稿质量低于 Nano。
- Whisper turbo 开头 60 秒较干净，但 CPU 上太慢，只有 GPU 或愿意等很久时再考虑。

## 关键实测对比

Nano 60s 主稿开头：

```text
规划大家都知道，十五规划呀，最近大家干得热火朝前。那针对国有企业，我们的十四五呢即将结束，十五马上就来了，我们怎么办呢？
```

Paraformer 同段：

```text
不，大家都知道十五规划呀，最近大家家干热热火朝天，那对对国企企我们的十四五呢即将结束。
```

SenseVoiceSmall 同段：

```text
哇大家都知道十五规划呀，最近大家干的热火朝前。那针对国有企业，我们的十四五呢即将结束，十5马上就来了...
```

Whisper turbo 60 秒样本：

```text
大家都知道十五规划最近大家干的热火朝前
那针对国有企业
我们的十四五即将结束
十五马上就来了
```

专名示例：

- Nano: `宁德时代`、`文心一言` 更接近正确。
- Paraformer: 出现 `赢德时代`、`文馨遗言`。
- SenseVoiceSmall: 能识别 `宁德时代`、`deep seek`，但混入 emoji 与数字化错误。
- Whisper turbo: 短样本未覆盖全部专名；开头可读性尚可。

## 推荐流程

### 1. 主稿

用 Nano 按 60 秒切块，再 8 路 shard 并行。不要直接用 2 分钟或 5 分钟块做最终稿；本录音上长块会触发复读和幻觉。

最终可读主稿：

```text
/home/timidly/funasr-cpu-demo/outputs/cao_junwu_nano_60s_parallel/results/transcript_5min_reading.md
```

结构化结果：

```text
/home/timidly/funasr-cpu-demo/outputs/cao_junwu_nano_60s_parallel/results/transcript.jsonl
```

### 2. 时间轴

用成熟 pipeline 跑：

```text
Paraformer + FSMN-VAD + CT-Punc + CAM++
```

输出：

```text
/home/timidly/funasr-cpu-demo/outputs/cao_junwu_paraformer_spk/full/paraformer_full_spk.md
/home/timidly/funasr-cpu-demo/outputs/cao_junwu_paraformer_spk/full/paraformer_full.json
```

注意：本录音的 `SPK0/SPK1` 不可靠，只适合作句级时间戳骨架。

### 3. 合并策略

实践上不要让 Paraformer 文本覆盖 Nano 文本。更稳的策略是：

1. 用 Paraformer 的 `sentence_info` 提供 `start/end`。
2. 把 Nano 60s 主稿按时间块映射到 Paraformer 时间轴。
3. 默认 speaker 折叠为主讲人。
4. 只对末尾、问答、主持人插话等疑似非主讲段做人工确认。

## 模型调用要点（实测过的 kwargs）

以下都是跑通过的关键参数，FunASR 的 README 不会单独强调；记下来主要是避免下次踩同样的坑。

### Fun-ASR-Nano

```python
AutoModel(
    model=<本地 modelscope 缓存目录>,  # 给 model_id 也行；指向本地缓存可避免 disable_update=True 时仍尝试联网
    trust_remote_code=True,
    remote_code="upstream/Fun-ASR/model.py",  # 必须 git clone FunAudioLLM/Fun-ASR 拿到这个文件
    device="cpu",
    disable_update=True,
)
model.generate(input=[<wav>], cache={}, language="中文",
               batch_size=1, hotwords=[], itn=True)
```

- `language` 用中文字面 `"中文"`，不是 `"zh"`。
- 长录音必须**先用外部工具预切成 60s `chunk_*.wav`** 再喂入，不能整段塞——长块会复读 / 幻觉（见上面 60s vs 2min vs 5min 对比）。
- 并行用进程级 shard 取模分配（`idx % num_shards == shard_index`），不要在一个进程里加 `batch_size`。每个 worker `torch.set_num_threads(8)`，8 worker 在本机 120 vCPU 上不互相打架。
- `hotwords` 只是参数 hook 但本录音没实际跑过；`itn` 默认 True。

### Paraformer 链（粗字幕 + 句级时间戳）

```python
AutoModel(
    model="paraformer-zh",
    vad_model="fsmn-vad",
    punc_model="ct-punc-c",   # ← 拉不到则 fallback 到 "ct-punc"
    spk_model="cam++",
    device="cpu",
)
model.generate(input=..., batch_size_s=300)  # 长录音用 300，短样本 60 即可
```

- `ct-punc-c` 在某些 ModelScope 镜像 / 老 funasr 上不存在，必须 try/except 退到 `ct-punc`，否则整条链起不来。
- 输出的 `sentence_info[i]` 含 `start/end/spk` 和 token 级 `timestamp`（毫秒），这就是要拿的字段。
- `spk` 在本录音里把单人切成 SPK0/SPK1，不可信——只用 `start/end`。

### SenseVoiceSmall（候选对照）

```python
AutoModel(
    model="iic/SenseVoiceSmall",
    vad_model="fsmn-vad",
    vad_kwargs={"max_single_segment_time": 30000},  # ms
    device="cpu",
)
model.generate(input=..., language="zh", use_itn=True,
               batch_size_s=60, merge_vad=True, merge_length_s=15)
```

- 输出含 emoji / 特殊 token，要用 `funasr.utils.postprocess_utils.rich_transcription_postprocess` 清洗后再读。
- `language` 这里是 `"zh"`（与 Nano 不一致），写 demo 时容易踩。

### Whisper turbo

只用 `whisper --model turbo` CLI 跑过 60 秒样本，没跑全量；CPU 上太慢，没再调 kwargs。

## 安装和环境经验

按本机约定用 `uv`，`.venv` 只是 `uv venv` 生成的环境目录，不代表用了标准库 `venv` 流程。

关键安装顺序（**torch 必须先用 CPU wheel 装，再装 funasr，否则 funasr 的依赖会拉 CUDA 版**）：

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu torch torchaudio
uv pip install --python .venv/bin/python funasr==1.3.1 modelscope huggingface_hub soundfile librosa transformers accelerate
uv pip install --python .venv/bin/python openai-whisper zhconv whisper_normalizer pyopenjtalk-plus compute-wer
git clone --depth 1 https://github.com/FunAudioLLM/Fun-ASR.git upstream/Fun-ASR  # Nano 必需，trust_remote_code 指向其 model.py
```

- `funasr==1.3.1` 锁版本，更高/更低和上述 kwargs 不一定兼容。

模型缓存落在：

```text
~/.cache/modelscope/hub/models/
```

已用模型包括：

```text
FunAudioLLM/Fun-ASR-Nano-2512
iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
iic/speech_fsmn_vad_zh-cn-16k-common-pytorch
iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
iic/speech_campplus_sv_zh-cn_16k-common
iic/SenseVoiceSmall
```

首跑后缓存体积大致：Nano ≈ 2.0 G、Paraformer ≈ 953 M、FSMN-VAD ≈ 3.9 M、CT-Punc ≈ 283 M、CAM++ ≈ 28 M。

在 Codex 沙箱里，FunASR/ModelScope 会尝试写 `~/.cache/modelscope/hub/.lock/...`，普通 sandbox 可能报只读文件系统。遇到这种情况直接用 escalated permission 重跑。

## 已有脚本

原 demo 目录 `/home/timidly/funasr-cpu-demo/scripts` 已废弃，下表是其中脚本的职责，作为日后重写的备忘：

| 脚本 | 用途 |
|---|---|
| `check_env.py` | 验证 venv / torch / funasr / 模型缓存是否就绪 |
| `nano_text_demo.py` | Nano 单段 smoke test（短音频 / URL） |
| `nano_batch_chunks.py` | Nano 分块批处理，支持 shard 并行 |
| `merge_nano_shards.py` | 合并 Nano 多 shard JSONL/Markdown |
| `group_transcript.py` | 把 60s Nano 块合并成 5min 阅读版 |
| `paraformer_spk_demo.py` | 跑 Paraformer + VAD + Punc + CAM++ |
| `paraformer_json_to_md.py` | 从 FunASR JSON 生成 speaker/timestamp Markdown |
| `group_paraformer_reading.py` | 把 Paraformer 句子合并成 5min 阅读版 |
| `sensevoice_text_demo.py` | 跑 SenseVoiceSmall 候选转写 |

## 速度记录

本录音总语音时长约 11605 秒。

| 方案 | 实测耗时 |
|---|---:|
| Nano 60s 8 路并行 | 最慢 shard 前向累计约 15-16 分钟 |
| Paraformer 全量 | 日志显示 12:07，`time_escape` 约 665 秒 |
| SenseVoiceSmall 全量 | 日志显示 6:24，`time_escape` 约 325 秒 |
| Whisper turbo 60 秒样本 | 约 2 分半 |

注意 Nano 的完整实验墙钟更长，因为中途试过 5min/2min、抽查、废弃、重跑 60s。

## 官方/社区依据

- FunASR SenseVoiceSmall 示例里 `language` 支持 `zn/en/yue/ja/ko/nospeech`，并说明 word-level timestamp 和 speaker identity 后续支持。
- OpenAI Whisper 官方讨论发布了 `large-v3-turbo`/`turbo`，它是针对推理速度优化的 `large-v3` 变体。
- Whisper 官方 README 支持 CLI 直接 `--model turbo`。

参考：

- https://github.com/modelscope/FunASR/blob/main/docs/tutorial/Tables.md
- https://github.com/openai/whisper/discussions/2363
- https://github.com/openai/whisper/blob/main/README.md
