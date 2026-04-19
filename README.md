# WhisperDictate

Lokální Superwhisper-style diktování pro macOS. Drž hotkey, mluv, pusť — text se přepíše přes [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) a vloží do pole, kde jsi naposledy stál.

Všechno běží lokálně na Apple Silicon, nic neodchází do cloudu.

## Co umí

- **Push-to-talk** — drž konfigurovatelný hotkey, pusť = přepis + vložení
- **Plovoucí overlay u kurzoru** s animovaným waveformem (červený při nahrávání, modrý při přepisu)
- **Zvuky** při startu/stopu nahrávání
- **Cílová aplikace zamčená při startu** — text se vloží do okna, kde jsi byl na začátku, i když mezitím přepneš jinam
- **Pause/resume hudby** (Music, Spotify) při nahrávání
- **Auto-paste** nebo jen do clipboardu
- **Nastavení modelu / jazyka / hotkey** přímo v menu baru
- **Autostart při přihlášení** (přes LaunchAgent nebo Login Item)

## Požadavky

- macOS 11+ na Apple Silicon (M1/M2/M3/…) — MLX nejede na Intelu
- Python 3.10+ doporučeno (3.9 funguje, ale `mlx-whisper` cílí na novější)
- [Homebrew](https://brew.sh) pokud potřebuješ novější Python

## Instalace

```sh
git clone <repo-url>
cd whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Pokud `python3` je 3.9 a narážíš na problémy:

```sh
brew install python@3.12
rm -rf .venv
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Spuštění (dev)

```sh
source .venv/bin/activate
python whisper_dictate.py
```

Při prvním spuštění:

1. **Mikrofon** — macOS se zeptá, povol.
2. **Accessibility + Input Monitoring** — jdi do **System Settings → Privacy & Security** a do obou přidej **Terminal.app** (nebo iTerm / Warp, podle toho, odkud pouštíš). Pak terminál úplně ukonči (⌘Q) a spusť znovu.
3. Model **large-v3-turbo** (~1.5 GB) se stáhne automaticky z HuggingFace do `~/.cache/huggingface/`.

Ovládání:

- Drž **pravý ⌘** (výchozí) → 🎙 → 🔴, mluv → pusť → ⏳ → text se vloží.
- Klikni na ikonu v menu baru pro nastavení.

## Autostart přes LaunchAgent

Nejspolehlivější cesta — nepotřebuje fungující .app:

```sh
./install_autostart.sh
```

Pak jdi do **System Settings → General → Login Items** a v sekci **Allow in the Background** zapni `com.sharkjohny.whisperdictate`. Bez toho macOS agent tiše zabije.

Odinstalace:

```sh
./uninstall_autostart.sh
```

## Build jako .app

```sh
./build_app.sh
open dist/
```

Přetáhni `WhisperDictate.app` do `/Applications`. Musíš znovu nastavit permissions — tentokrát pro samotnou appku:

- **Privacy & Security → Microphone** — přidej `WhisperDictate.app`
- **Privacy & Security → Accessibility** — přidej `WhisperDictate.app`
- **Privacy & Security → Input Monitoring** — přidej `WhisperDictate.app`

Pak v menu appky klikni **Start at login** pro autostart.

**Poznámka:** .app je jen tenký shell launcher, který volá `.venv/bin/python whisper_dictate.py`. Když přesuneš složku projektu, přestane fungovat — spusť znovu `./build_app.sh`.

## Konfigurace

Uložená v `~/Library/Application Support/WhisperDictate/config.json` — přepíše se automaticky, když kliknutím v menu změníš jakoukoli volbu.

| Volba         | Možnosti                                                              |
|---------------|----------------------------------------------------------------------|
| `hotkey`      | `cmd_r` / `cmd_l` / `alt_r` / `alt_l` / `ctrl_r` / `f13` / `f18` / `f19` |
| `model`       | `mlx-community/whisper-{tiny,base,small,medium,large-v3}-mlx` nebo `…/whisper-large-v3-turbo` |
| `language`    | `cs` / `en` / `sk` / `de` / `fr` / `es` nebo `null` (auto-detect)    |
| `play_sounds` | `true` / `false`                                                      |
| `auto_paste`  | `true` = Cmd+V, `false` = jen do clipboardu                           |
| `pause_media` | `true` / `false`                                                      |

## Troubleshooting

- **„This process is not trusted" na startu** — chybí Accessibility permission. Přidej Terminal / .app do System Settings → Privacy & Security → Accessibility, ukonči terminál a spusť znovu.
- **Hotkey nefunguje** — chybí Input Monitoring permission.
- **Text se nevloží, ale v clipboardu je** — Auto-paste je vypnuté, nebo cílová appka odmítla Cmd+V. Zkus ručně.
- **`FileNotFoundError: ffmpeg`** — už nemělo nastat, ale pokud ano, audio se predává jako numpy array, `brew install ffmpeg` to taky vyřeší.
- **`trace trap` / SIGTRAP** — AppKit volání z pozadí; pokud se to vrátí, je to regrese a napiš issue.
- **LaunchAgent neběží** — zkontroluj, jestli je povolený v Login Items → Allow in the Background. Log: `/tmp/whisperdictate.log`.

## Jak to funguje uvnitř

- `mlx-whisper` na Apple Silicon GPU — model `large-v3-turbo` přepíše ~1 min audia za pár sekund
- `sounddevice` pro nahrávání z mikrofonu (16 kHz, mono)
- `pynput` pro globální hotkey a simulaci Cmd+V
- `rumps` (nad PyObjC) pro menu bar
- AppKit přímo (přes PyObjC) pro plovoucí overlay s waveformem
- AppleScript přes `osascript` pro Music/Spotify pause a Login Items

## Licence

MIT (viz `LICENSE`).
