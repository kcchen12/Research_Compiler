from __future__ import annotations

import html
import json
import re


def digest_to_speech_text(markdown_text: str) -> str:
    """Convert digest Markdown into cleaner text for browser speech synthesis."""
    text = markdown_text or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~>|]+", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_audio_reader_html(speech_text: str) -> str:
    text_json = json.dumps(speech_text or "")
    return f"""
<div class="reader-shell">
  <div class="reader-toolbar">
    <button type="button" id="play">Play</button>
    <button type="button" id="pause">Pause</button>
    <button type="button" id="resume">Resume</button>
    <button type="button" id="stop">Stop</button>
    <label>
      Speed
      <input id="rate" type="range" min="0.75" max="1.5" value="1" step="0.05" />
      <span id="rateValue">1.00x</span>
    </label>
  </div>
  <p id="status">Ready to read the current digest.</p>
</div>
<script>
const digestText = {text_json};
const statusEl = document.getElementById("status");
const rate = document.getElementById("rate");
const rateValue = document.getElementById("rateValue");
let utterance = null;

function canRead() {{
  return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}}

function stopReading() {{
  if (canRead()) {{
    window.speechSynthesis.cancel();
  }}
  utterance = null;
}}

function setStatus(message) {{
  statusEl.textContent = message;
}}

rate.addEventListener("input", () => {{
  rateValue.textContent = `${{Number(rate.value).toFixed(2)}}x`;
}});

document.getElementById("play").addEventListener("click", () => {{
  if (!canRead()) {{
    setStatus("Audio reading is not supported in this browser.");
    return;
  }}
  if (!digestText.trim()) {{
    setStatus("There is no digest text to read yet.");
    return;
  }}
  stopReading();
  utterance = new SpeechSynthesisUtterance(digestText);
  utterance.rate = Number(rate.value);
  utterance.pitch = 1;
  utterance.onstart = () => setStatus("Reading digest...");
  utterance.onpause = () => setStatus("Paused.");
  utterance.onresume = () => setStatus("Reading digest...");
  utterance.onend = () => setStatus("Finished.");
  utterance.onerror = () => setStatus("Audio reading stopped.");
  window.speechSynthesis.speak(utterance);
}});

document.getElementById("pause").addEventListener("click", () => {{
  if (canRead()) window.speechSynthesis.pause();
}});

document.getElementById("resume").addEventListener("click", () => {{
  if (canRead()) window.speechSynthesis.resume();
}});

document.getElementById("stop").addEventListener("click", () => {{
  stopReading();
  setStatus("Stopped.");
}});

window.addEventListener("pagehide", stopReading);
</script>
<style>
  .reader-shell {{
    border: 1px solid #d8dde6;
    border-radius: 8px;
    box-sizing: border-box;
    color: #172033;
    font: 14px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    padding: 12px;
  }}
  .reader-toolbar {{
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }}
  button {{
    background: #172033;
    border: 1px solid #172033;
    border-radius: 6px;
    color: white;
    cursor: pointer;
    font: inherit;
    min-height: 34px;
    padding: 6px 12px;
  }}
  button:hover {{
    background: #2e3a52;
  }}
  label {{
    align-items: center;
    display: inline-flex;
    gap: 8px;
    margin-left: 4px;
  }}
  input {{
    accent-color: #172033;
  }}
  p {{
    color: #536071;
    margin: 10px 0 0;
  }}
</style>
"""
