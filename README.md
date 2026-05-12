# PTT Alertor

PTT 文章通知 bot，私訊 Discord 推播。原 Go 版已重寫為 Python，跑在 macOS 背景。

➡️ **詳細說明與安裝步驟**：[python/README.md](python/README.md)

## 快速啟動

```bash
cd python
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env       # 編輯填入 DISCORD_TOKEN / AUTH_PW
.venv/bin/python -m ptt_alertor
```

## 目錄結構

```
.
├── python/          # ⬅ Python 重構版（唯一活躍實作）
│   ├── ptt_alertor/  # source
│   ├── tests/
│   ├── deploy/       # LaunchAgent plist + install/uninstall
│   ├── pyproject.toml
│   ├── .env.example
│   └── README.md
├── LICENSE
└── README.md (this file)
```

舊的 Go 程式碼已從 master 移除，需要時可以從 `backup/before-python-rewrite` 分支取回。
