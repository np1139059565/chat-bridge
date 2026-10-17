"""远程桥接 —— 音频编码（WAV 转 MP3）

职责：把各语音引擎产出的 WAV 统一编码为 MP3，供发送与播放。

为什么需要本模块：
- edge-tts 直接产出 MP3；piper 与 pyttsx3 只产出 WAV。
- 上游（message_voice / web_mirror）一律按 .mp3 处理，格式必须统一。
- 本机未安装 ffmpeg，故用 soundfile 读取 + lameenc 编码，纯 Python 完成。

采样率处理：
- MP3 只支持固定的若干采样率（见 MP3_RATES）。
- 输入采样率不在其中时，用线性插值重采样到最接近的标准采样率。

依赖：os、shutil、numpy（重采样）、soundfile（读 WAV）、lameenc（编码）
"""
import os
import shutil


# MP3 编码器支持的采样率白名单；不在其中的输入需先重采样。
MP3_RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)


def _resample(pcm, src_rate, dst_rate, channels):
    """线性插值重采样，把任意采样率的 PCM 转到目标采样率。

    仅在源采样率不在 MP3 白名单时使用；用 numpy 实现，不引入额外依赖。
    @param pcm      交错排列的 int16 PCM 字节
    @param src_rate 源采样率
    @param dst_rate 目标采样率
    @param channels 声道数
    @returns 重采样后的 PCM 字节
    """
    import numpy as np
    # 还原为 (帧数, 声道) 的整型数组
    data = np.frombuffer(pcm, dtype=np.int16).reshape(-1, channels)
    n_src = data.shape[0]                                   # 源帧数
    n_dst = int(round(n_src * dst_rate / float(src_rate)))  # 目标帧数
    if n_dst <= 0:
        return b""
    # 源帧与目标帧的下标映射，再做线性插值
    src_idx = np.linspace(0, n_src - 1, n_dst)
    lo = np.floor(src_idx).astype(np.int64)                 # 下取整索引
    hi = np.minimum(lo + 1, n_src - 1)                      # 上取整索引（末尾夹紧）
    frac = (src_idx - lo).reshape(-1, 1)                    # 插值权重
    out = data[lo] * (1.0 - frac) + data[hi] * frac         # 逐声道线性插值
    return out.astype(np.int16).tobytes()                   # 回到 int16 字节流


def ensure_mp3(src_path, dst_mp3):
    """把一个音频文件编码为 MP3，写到 dst_mp3。

    已带 .mp3 后缀的输入直接移动；WAV 输入用 soundfile 读取、
    必要时重采样，再交给 lameenc 编码。全程不依赖 ffmpeg。
    @param src_path 源音频路径（WAV 或 MP3）
    @param dst_mp3  目标 MP3 路径
    @returns (ok, error)；成功时 error 为空串
    """
    # 源已是 MP3：直接搬到目标位置，省去重编码
    if str(src_path).lower().endswith(".mp3"):
        try:
            shutil.move(src_path, dst_mp3)
            return True, ""
        except Exception as e:
            return False, "移动 MP3 失败：%s" % e

    try:
        import lameenc          # MP3 编码器（PyPI 有 Windows 预编译包）
        import soundfile as sf  # WAV 读取，兼容多种位深与声道布局
    except Exception as e:
        return False, "缺少音频编码依赖：%s" % e

    try:
        # 统一读成 float64 波形与采样率；always_2d 保证二维形状
        data, rate = sf.read(src_path, dtype="float64", always_2d=True)
        channels = data.shape[1]                            # 声道数
        if channels not in (1, 2):
            # MP3 只支持单声道与立体声；多声道取前两路，其余丢弃
            data = data[:, :2]
            channels = data.shape[1]
        if rate not in MP3_RATES:
            # 采样率不在 MP3 支持列表：选最接近的标准采样率并重采样
            dst_rate = min(MP3_RATES, key=lambda r: abs(r - rate))
            pcm = (data * 32767.0).clip(-32768, 32767).astype("int16").tobytes()
            pcm = _resample(pcm, rate, dst_rate, channels)
            rate = dst_rate
        else:
            # 采样率可用：直接量化为 16 位整型字节流
            pcm = (data * 32767.0).clip(-32768, 32767).astype("int16").tobytes()

        enc = lameenc.Encoder()                             # 新建编码器实例
        enc.set_bit_rate(128)                               # 128 kbps，语音足够
        enc.set_in_sample_rate(int(rate))                   # 输入采样率
        enc.set_channels(int(channels))                     # 声道数
        enc.set_quality(2)                                  # 0 最高质量、9 最快
        out = enc.encode(pcm)                               # 主体编码
        out += enc.flush()                                  # 冲刷尾部数据
        if not out:
            return False, "MP3 编码结果为空"
        with open(dst_mp3, "wb") as fh:                    # 落盘
            fh.write(out)
        return True, ""
    except Exception as e:
        return False, "WAV 转 MP3 失败：%s" % e
