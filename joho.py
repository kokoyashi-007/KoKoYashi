import streamlit as st
import pandas as pd
import numpy as np
import time
import os
import re
import math
import html
import json
import google.generativeai as genai
from janome.tokenizer import Tokenizer

# =========================================================
# 0. アプリケーション設定 & CSS
# =========================================================
st.set_page_config(page_title="CineLog AI ", layout="wide")

st.markdown("""
<style>
    /* ベースデザイン */
    body {
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
        background-color: #FAFAFA; color: #333;
    }
    h1 {
        background: linear-gradient(45deg, #2C3E50, #4CA1AF);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-weight: 800; letter-spacing: -1px; margin-bottom: 0.5rem;
    }
    
    /* タイムライン表示 */
    .timeline-container { position: relative; padding: 20px 0; }
    .timeline-container::before { content: ''; position: absolute; top: 0; bottom: 0; left: 80px; width: 2px; background: #E0E0E0; }
    
    .timeline-item { position: relative; margin-bottom: 24px; display: flex; align-items: flex-start; }
    .timeline-time { width: 70px; text-align: right; padding-right: 20px; font-family: 'Courier New', monospace; font-weight: bold; color: #888; font-size: 0.9rem; padding-top: 4px; }
    .timeline-marker { position: absolute; left: 74px; width: 14px; height: 14px; border-radius: 50%; background: #FFF; border: 3px solid #ccc; z-index: 1; margin-top: 5px; }
    .timeline-content { flex: 1; margin-left: 30px; background: #FFF; border-radius: 12px; padding: 16px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-left: 5px solid #ccc; transition: transform 0.2s; color: #333; }
    
    .marker-pos { border-color: #4CA1AF; } .border-pos { border-left-color: #4CA1AF; }
    .marker-neg { border-color: #FF6B6B; } .border-neg { border-left-color: #FF6B6B; }
    .marker-mark { border-color: #f6ad55; } .border-mark { border-left-color: #f6ad55; }
    
    /* ステージタグ */
    .stage-tag {
        display: inline-block; padding: 2px 8px; border-radius: 4px; 
        font-size: 0.75rem; font-weight: bold; color: #555; background: #eee;
        border: 1px solid #ddd;
    }

    /* 辞書判定詳細チップ */
    .chip {
        display: inline-block; padding: 2px 8px; margin: 2px;
        border-radius: 12px; font-size: 0.75rem; border: 1px solid #ddd; background: #fff; vertical-align: middle;
    }
    .chip-pos { border-color: #b2f5ea; color: #006d5b; background: #e6fffa; }
    .chip-neg { border-color: #fed7d7; color: #c53030; background: #fff5f5; }
    
    /* チャットエリア */
    .chat-container { border-top: 2px solid #eee; padding-top: 20px; margin-top: 30px; }
    
    /* ガイドボックス */
    .guide-box {
        background-color: #e3f2fd; border-radius: 8px; padding: 15px;
        border-left: 5px solid #2196F3; margin-bottom: 20px;
        font-size: 0.9rem; color: #0d47a1;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 1. Janome & 辞書ロジック (拡張版)
# =========================================================

NEGATION_WORDS = ['ない', 'ぬ', 'ず', 'ん', 'まい']
ADVERSATIVE_WORDS = ['しかし', 'でも', 'だが', 'けれど', 'けども', 'ところが']
COMPOUND_RULES = {
    ('全く', '良い'): 0.0, ('非常に', '良い'): 1.2, ('とても', '良い'): 1.2,
    ('すごく', '良い'): 1.2, ('あまり', '良い'): 0.2, ('全然', '良い'): 1.5,
}

@st.cache_resource
def get_tokenizer():
    return Tokenizer()

@st.cache_resource
def load_sentiment_dictionary():
    """複数の辞書ファイルを読み込んで統合する"""
    dict_files = [
        {'name': 'pn_ja.dic', 'enc': 'shift-jis', 'sep': ':', 'cols': [0, 3]},
        {'name': 'wago.121808.pn', 'enc': 'utf-8', 'sep': '\t', 'cols': [1, 0]},
        {'name': 'pn.csv.m3.120408.trim', 'enc': 'utf-8', 'sep': '\t', 'cols': [0, 1]}
    ]
    
    dic_data = {}
    loaded_files = []
    
    for d in dict_files:
        path = d['name']
        if not os.path.exists(path):
            path = os.path.join('dic', d['name'])
        
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, encoding=d['enc'], sep=d['sep'], header=None, on_bad_lines='skip')
                term_col = d['cols'][0]
                score_col = d['cols'][1]
                
                if len(df.columns) > max(term_col, score_col):
                    for _, row in df.iterrows():
                        term = str(row[term_col]).strip()
                        val = row[score_col]
                        score = 0.0
                        if isinstance(val, (int, float)):
                            score = float(val)
                        elif isinstance(val, str):
                            val = val.lower().strip()
                            if val in ['p', 'pos', 'positive']: score = 1.0
                            elif val in ['n', 'neg', 'negative']: score = -1.0
                            elif val in ['e', 'neu', 'neutral']: score = 0.0
                            else:
                                try: score = float(val)
                                except: pass
                        dic_data[term] = score
                    loaded_files.append(d['name'])
            except Exception as e:
                pass

    if not dic_data:
        dic_data = {'良い': 1.0, '悪い': -1.0, '好き': 1.0, '嫌い': -1.0, '楽しい': 0.9, '退屈': -0.9}
        
    return dic_data, loaded_files

SENTIMENT_DICT, LOADED_DICTS = load_sentiment_dictionary()

def analyze_sentiment_advanced(text):
    if not text: return 0.0, []
    text_norm = text.replace("ありません", "ないです")
    t = get_tokenizer()
    tokens = list(t.tokenize(text_norm))
    matched_scores = []
    calc_log = [] 
    current_boost = 1.0
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        base_form = token.base_form
        pos_part = token.part_of_speech.split(',')
        pos = pos_part[0]
        sub_pos = pos_part[1] if len(pos_part) > 1 else ""
        
        if (pos == '接続詞' and base_form in ADVERSATIVE_WORDS) or \
           (pos == '助詞' and sub_pos == '接続助詞' and base_form in ['が', 'けど', 'けれど', 'けれども']):
            current_boost = 1.5
            calc_log.append({'term': base_form, 'score': 0, 'reason': '逆接(x1.5)', 'weight': 0, 'boost': current_boost})
        
        current_score = 0.0
        found_sentiment = False
        reason = ""
        matched_term = base_form
        
        if pos in ['形容詞', '動詞', '名詞']:
            for j in range(1, 5):
                if i - j >= 0:
                    prev_base = tokens[i-j].base_form
                    if (prev_base, base_form) in COMPOUND_RULES:
                        current_score = COMPOUND_RULES[(prev_base, base_form)]
                        found_sentiment = True
                        matched_term = f"{prev_base}+{base_form}"
                        reason = "連語"
                        break
        
        if not found_sentiment and base_form in SENTIMENT_DICT:
            if pos in ['名詞', '動詞', '形容詞', '副詞', '連体詞']:
                current_score = float(SENTIMENT_DICT[base_form])
                found_sentiment = True
                reason = "辞書"
        
        if found_sentiment:
            negated = False
            neg_term = ""
            for k in range(1, 4):
                if i + k < len(tokens):
                    nb = tokens[i+k].base_form
                    if nb in NEGATION_WORDS: negated = True; neg_term=nb; break
                    if nb in ['。', '、', '！', 'EOS']: break
            if negated:
                current_score *= -1.0
                reason += f" ➡ 否定「{neg_term}」"
            
            final_weight = 1.0 * current_boost
            matched_scores.append({'score': current_score, 'weight': final_weight})
            calc_log.append({'term': matched_term, 'score': current_score, 'reason': reason, 'weight': final_weight, 'boost': current_boost})
            
        i += 1
        
    if not matched_scores: return 0.0, calc_log
    weighted_sum = sum(item['score'] * item['weight'] for item in matched_scores)
    total_weight = sum(item['weight'] for item in matched_scores)
    final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    return max(-1.0, min(1.0, final_score)), calc_log

# =========================================================
# 2. ステート & AI知識ベース
# =========================================================

if 'status' not in st.session_state: st.session_state.status = 'ready'
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'elapsed_offset' not in st.session_state: st.session_state.elapsed_offset = 0.0
if 'notes' not in st.session_state: st.session_state.notes = []
if 'gemini_api_key' not in st.session_state: st.session_state.gemini_api_key = ""
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'characters' not in st.session_state: st.session_state.characters = [] 
if 'chat_initialized' not in st.session_state: st.session_state.chat_initialized = False
if 'compare_data' not in st.session_state: st.session_state.compare_data = None
if 'compare_title' not in st.session_state: st.session_state.compare_title = ""

KNOWLEDGE_STRUCTURE = """
【物語構造分析知識ベース (Composite Narrative Analysis)】

■ 1. マクロ構造フレームワーク
* **三幕構成**: 設定(Act1) → 対立(Act2) → 解決(Act3)
* **起承転結**: 導入(起) → 展開(承) → 飛躍・逆転(転) → 結末(結)
* **行って帰る**: 「日常」から「非日常」への境界を超え、試練を経て変化し、再び「日常」へ帰還する円環構造。

■ 2. 物語の内容モデル (状態変化 S1 → M → S2)
物語のミクロな連鎖は「初期状態(S1) → 手段(M) → 帰結状態(S2)」で定義される。
* **初期状態 (S1)**: 主人公の困った状態（欠落）。
* **手段・方法 (M)**: S1から脱するためにとる行動。
* **帰結状態 (S2)**: 行動の結果至った状態。

**重視する変化パターン:**
a. プラス → マイナス (転落)
b. マイナス → プラス (回復)
c. 義務・欲望 → 行為
d. 無知 → 認識 (発見)
e. 認識 → 現表行為
f. 行為 → その評価

■ 3. 和語・表現の評価基準 (kijun.pdfに基づく)
文脈分析において以下の基準を適用すること。
* **経験 vs 評価**: 話し手自身の体験か、対象への客観評価かを区別する。
* **受動態 (レル/ラレル) の解釈**: 
    * **可能**: 能力や許容はポジティブ傾向。
    * **恩恵受け身**: 「誘ってもらった」はポジティブ。
    * **迷惑受け身**: 「荒らされた」はネガティブ。

■ 4. 表現技法 (Discourse)
* **没入**: 自己移入、感情移入。
* **時間**: 省略法、要約法、情景法、描写的休止法。
* **叙法**: 非焦点化、内的焦点化、外的焦点化。

■ 5. 物語構造分析チェックリスト
1. プロットの核 / 2. 主人公(欠落) / 3. 現在位置 / 4. 過去 / 5. クエストと目的
6. 象徴的獲得・喪失 / 7. 敵対者 / 8. 協力者 / 9. 日常世界 / 10. 変化を促す存在
11. 旅の最深部 / 12. 喪失 / 13. 最終局面 / 14. 結末
"""

WALL_PARTNER_PROMPT = f"""
あなたは「物語構造分析の壁打ちパートナー」です。
ユーザーの入力に基づき、提供された知識ベース（三幕構成、起承転結、行って帰る、S1→M→S2モデルなど）を複合的に活用して分析を深堀りしてください。

【あなたの役割】
ユーザーの意見を安易に肯定せず、構造的な視点から鋭い問いを投げかけること。

【★隠し評価基準：専門用語への感度】
ユーザーの『感情(Feeling)』の中に、以下の専門的な要素に関する言及が含まれていた場合、「そこに気づくとは素晴らしい視点です」「音響効果への言及、鋭いですね」と**具体的に褒めて**ください。
- **演出** (Direction), **演技** (Acting), **映像** (Visual), **音響** (Sound), **脚本/ストーリー** (Story)

【知識ベース】
{KNOWLEDGE_STRUCTURE}
"""

# =========================================================
# 3. 分析・ヘルパー関数
# =========================================================

def analyze_scene_with_ai(plot_text, emotion_text):
    dict_score, calc_log = analyze_sentiment_advanced(emotion_text)
    
    log_summary = "検出語なし"
    if calc_log:
        items = [f"{item['term']}({item['score']})" for item in calc_log if item.get('weight', 0) > 0]
        log_summary = ", ".join(items)
    
    dict_info = f"辞書計算値: {dict_score:.3f} (根拠: {log_summary})"
    
    api_key = st.session_state.gemini_api_key
    if not api_key:
        return dict_score, "API未設定", "辞書判定", "なし", calc_log

    try:
        genai.configure(api_key=api_key)
        # モデル名: gemini-2.0-flash
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = f"""
        あなたは物語分析の専門家です。以下のシーンを分析しJSONで出力してください。
        
        【タスク】
        1. 辞書判定スコア({dict_score})を参考に、文脈を考慮して最終スコアを決定。
           特に「kijun.pdf」基準にある「受動態の恩恵/迷惑」や「経験/評価」の区別に注意してください。
        2. あらすじ(Fact)から、知識ベースにある「変化パターン」「表現技法」「構造的位置」を分析。
        
        【★隠し評価ミッション】
        もし感情(Feeling)の中に「音響」「照明」「カメラ」「演技」「構成」などの専門的な要素への言及があれば、reasonの中で褒めてください。

        【入力】
        - 辞書判定: {dict_info}
        - あらすじ(Fact): {plot_text}
        - 感情(Feeling): {emotion_text}
        
        【知識ベース】
        {KNOWLEDGE_STRUCTURE}
        
        JSON出力:
        {{ 
            "final_score": -1.0〜1.0, 
            "pattern": "変化パターン", 
            "technique": "技法/構造", 
            "reason": "分析コメント(30文字程度)" 
        }}
        """
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        result = json.loads(response.text)
        return float(result.get("final_score", dict_score)), result.get("reason", ""), result.get("pattern", "その他"), result.get("technique", ""), calc_log
    except Exception as e:
        err_msg = str(e)
        if "404" in err_msg:
            return dict_score, "AIエラー: モデルが見つかりません(404)。APIキーの設定またはモデル名(gemini-2.0-flash)を確認してください。", "辞書判定", "", calc_log
        return dict_score, f"AIエラー: {err_msg[:20]}...", "辞書判定", "", calc_log

def chat_with_ai(user_message):
    api_key = st.session_state.gemini_api_key
    if not api_key: return "APIキーを設定してください。"
    history = [{"role": "system", "parts": [WALL_PARTNER_PROMPT]}]
    
    if st.session_state.notes:
        notes_context = "【現在の作品の分析ログ】\n"
        for note in st.session_state.notes[-5:]: 
            notes_context += f"- [{note['display_time']}] Pattern:{note['stage']} / Feeling:{note['emotion_content']}\n"
        history.append({"role": "user", "parts": [notes_context]})
    
    if st.session_state.compare_data is not None:
        comp_df = st.session_state.compare_data
        comp_title = st.session_state.compare_title
        avg_score = comp_df['sentiment'].mean()
        n = len(comp_df)
        indices = [0, n//2, n-1] if n > 0 else []
        digest = ""
        for i in indices:
            if i < n:
                row = comp_df.iloc[i]
                digest += f"- T={row.get('display_time','?')} Score={row.get('sentiment',0):.2f} Plot={row.get('plot','')[:20]}...\n"
        
        compare_context = f"【比較対象: {comp_title}】\n平均スコア: {avg_score:.2f}\n断片: {digest}"
        history.append({"role": "user", "parts": [compare_context]})

    history.append({"role": "model", "parts": ["了解しました。"]})

    for msg in st.session_state.chat_history:
        role = "user" if msg["role"] == "user" else "model"
        history.append({"role": role, "parts": [msg["content"]]})
    history.append({"role": "user", "parts": [user_message]})
    
    try:
        genai.configure(api_key=api_key)
        # モデル名: gemini-2.0-flash
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(history)
        return response.text
    except Exception as e:
        if "404" in str(e):
            return "エラー: AIモデル(gemini-2.0-flash)が見つかりません(404)。APIキーの設定またはモデル名を確認してください。"
        return f"エラー: {str(e)}"

def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def calculate_decay_curve(df_notes, duration):
    max_time = int(duration) + 1
    decay_scores = np.zeros(max_time)
    events = {int(row['timestamp']): row['sentiment'] for _, row in df_notes.iterrows() if int(row['timestamp']) < max_time}
    LIFETIME = 60.0; last_t = -999; last_s = 0.0
    for t in range(max_time):
        if t in events: decay_scores[t] = events[t]; last_t = t; last_s = events[t]
        elif last_t != -999:
            delta = t - last_t
            if delta < LIFETIME: decay_scores[t] = last_s * math.cos((math.pi/2)*(delta/LIFETIME))
    return pd.DataFrame({'timestamp': np.arange(max_time), 'sentiment': decay_scores})

def generate_html_report(df, title, chars):
    rows_html = ""
    for _, row in df.sort_values('timestamp').iterrows():
        score = row['sentiment']
        border_color = '#4CA1AF' if score >= 0.1 else '#FF6B6B' if score <= -0.1 else '#aaa'
        bg_color = '#f0fcf9' if score >= 0.1 else '#fff5f5' if score <= -0.1 else '#fff'
        
        chips_html = ""
        if row.get('calc_log'):
            for item in row['calc_log']:
                if item.get('weight', 0) > 0:
                    c_col = "#006d5b" if item['score'] > 0 else "#c53030"
                    c_bg = "#b2f5ea" if item['score'] > 0 else "#fed7d7"
                    chips_html += f"<span style='display:inline-block;padding:2px 6px;margin:1px;border-radius:10px;font-size:0.7em;background:{c_bg};color:{c_col};border:1px solid {c_col}'>{html.escape(item['term'])} {item['score']}</span>"
                elif '逆接' in item.get('reason', ''):
                    chips_html += f"<span style='display:inline-block;padding:2px 6px;margin:1px;border-radius:10px;font-size:0.7em;background:#fff3cd;color:#856404;border:1px solid #ffeeba'>逆接</span>"
        
        ai_comment = html.escape(row.get('comment', ''))
        rows_html += f"""
        <div style="border-left:5px solid {border_color}; background:{bg_color}; padding:15px; margin-bottom:15px; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <div><span style="font-family:monospace; font-weight:bold; color:#666;">{row['display_time']}</span> <span style="background:#e2e8f0; padding:2px 8px; border-radius:4px; font-size:0.8em;">{row['stage']}</span></div>
                <strong style="color:{border_color}">{score:+.2f}</strong>
            </div>
            <div style="margin-bottom:8px;">
                <div style="font-size:1.1em; font-weight:bold; margin-bottom:4px;">💭 {html.escape(row['emotion_content'])}</div>
                {f"<div style='font-size:0.9em; color:#666; font-style:italic;'>📖 {html.escape(row.get('plot',''))}</div>" if row.get('plot') else ""}
            </div>
            <div style="border-top:1px dashed #ccc; padding-top:8px; font-size:0.9em;">
                <div style="margin-bottom:4px;">🤖 <b>AI Comment:</b> {ai_comment}</div>
                <div>📚 <b>Dict Basis:</b> {chips_html if chips_html else "<span style='color:#999'>None</span>"}</div>
            </div>
        </div>"""
    
    display_title = html.escape(title) if title else "Analysis"
    return f"<html><body style='font-family:sans-serif;padding:20px;'><h1>🎬 {display_title} Report</h1>{rows_html}</body></html>"

def init_chat_with_analysis(df):
    st.session_state.chat_initialized = True

# =========================================================
# 4. メインUI
# =========================================================
with st.sidebar:
    st.header("⚙️ 設定")
    api_key_input = st.text_input("Gemini API Key", type="password", value=st.session_state.gemini_api_key)
    if api_key_input: st.session_state.gemini_api_key = api_key_input
    
    st.divider()
    
    # --- 比較データ読み込み機能 ---
    with st.expander("📂 比較・過去データ読込"):
        st.info("過去に保存したCSVファイルを読み込むと、グラフを重ねて比較できます。")
        uploaded_file = st.file_uploader("比較用CSVファイル", type=["csv"])
        if uploaded_file is not None:
            try:
                compare_df = pd.read_csv(uploaded_file)
                if 'timestamp' in compare_df.columns and 'sentiment' in compare_df.columns:
                    st.session_state.compare_data = compare_df
                    st.session_state.compare_title = uploaded_file.name.replace("_data.csv", "")
                    st.success(f"『{st.session_state.compare_title}』をロードしました")
                else:
                    st.error("CSVの形式が正しくありません")
            except Exception as e:
                st.error(f"読込エラー: {e}")
        
        if st.button("比較データをクリア"):
            st.session_state.compare_data = None
            st.session_state.compare_title = ""
            st.rerun()
    
    st.divider()
    with st.expander("📚 知識ベース確認"): st.markdown(KNOWLEDGE_STRUCTURE)
    
    st.divider()
    # 新しい分析を始めるボタン
    if st.button("🗑️ 新しい分析を始める (リセット)", type="primary", use_container_width=True):
        for key in ['status', 'start_time', 'elapsed_offset', 'notes', 'chat_history', 'chat_initialized', 'characters', 'compare_data', 'compare_title']:
             if key in st.session_state: del st.session_state[key]
        st.rerun()

st.title("🎬 CineLog ")
movie_title = st.text_input("作品名", placeholder="作品名を入力", label_visibility="collapsed")

# プレイヤー制御
c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
current_time = st.session_state.elapsed_offset
if st.session_state.status == 'playing': current_time += time.time() - st.session_state.start_time

with c1:
    if st.button("▶ 開始/再開", type="primary", use_container_width=True, disabled=(st.session_state.status == 'playing')):
        st.session_state.status = 'playing'; st.session_state.start_time = time.time(); st.rerun()
with c2:
    if st.button("⏸ 一時停止", use_container_width=True, disabled=(st.session_state.status != 'playing')):
        st.session_state.status = 'paused'; st.session_state.elapsed_offset += time.time() - st.session_state.start_time; st.rerun()
with c3: st.metric("Time", format_time(current_time), label_visibility="collapsed")
with c4:
    if st.button("■ 終了/分析", type="secondary", use_container_width=True, disabled=(st.session_state.status == 'ready')):
        if st.session_state.status == 'playing': st.session_state.elapsed_offset += time.time() - st.session_state.start_time
        st.session_state.status = 'finished'; st.rerun()

# 入力フォーム
if st.session_state.status in ['playing', 'paused']:
    st.divider()
    st.info("💡 **使い分け**: 💭 **感情(Feeling)**はあなたの心の動きのグラフ化に使われます / 📖 **あらすじ(Fact)**は物語の出来事は構造分析に使われます")
    
    with st.form("log_form", clear_on_submit=True):
        c_plot, c_emo = st.columns(2)
        plot = c_plot.text_area("📖 Fact (あらすじ/出来事)", height=100, placeholder="主人公が〇〇をした、××が起きた")
        emo = c_emo.text_area("💭 Feeling (感想/感情)", height=100, placeholder="ここで感動した、ハラハラした")
        
        if st.form_submit_button("記録 & 分析", type="primary", use_container_width=True):
            if plot or emo:
                ts = current_time
                sc, rsn, pat, tch, log = analyze_scene_with_ai(plot, emo)
                st.session_state.notes.append({
                    "timestamp": ts, "display_time": format_time(ts),
                    "plot": plot, "emotion_content": emo, 
                    "sentiment": sc, "stage": pat, "technique": tch, "comment": rsn, "calc_log": log
                })
                st.toast("記録・分析完了", icon="✅")

# 結果表示画面 (Finishedモード)
if st.session_state.status == 'finished':
    st.divider()
    st.header("📊 分析レポート")
    
    if not st.session_state.notes:
        st.warning("記録されたメモがありません。")
    else:
        df = pd.DataFrame(st.session_state.notes)
        
        # 1. 感情曲線
        st.subheader("1. 感情曲線 (User Feeling)")
        st.caption("入力された**「感情(Feeling)」**に基づいて算出された、あなたの心の動きです。")
        
        max_time_current = max(st.session_state.elapsed_offset, df['timestamp'].max()) if not df.empty else 60
        max_time_compare = st.session_state.compare_data['timestamp'].max() if st.session_state.compare_data is not None else 0
        final_max_time = max(max_time_current, max_time_compare)
        if final_max_time == 0: final_max_time = 60

        df_decay_current = calculate_decay_curve(df, final_max_time)
        df_decay_current = df_decay_current.set_index('timestamp')
        df_decay_current.columns = ['Current']

        if st.session_state.compare_data is not None:
            df_decay_compare = calculate_decay_curve(st.session_state.compare_data, final_max_time)
            df_decay_compare = df_decay_compare.set_index('timestamp')
            df_decay_compare.columns = [f"Compare: {st.session_state.compare_title}"]
            st.line_chart(pd.concat([df_decay_current, df_decay_compare], axis=1))
            st.success(f"📈 『{st.session_state.compare_title}』と比較中")
        else:
            st.line_chart(df_decay_current, color="#FF4B4B")

        st.write("")
        
        # 2. タイムライン
        st.subheader("2. 物語構造分析 (Story Structure)")
        st.caption("入力された**「あらすじ(Fact)」**に基づいてAIが分析した、物語の構成要素と雰囲気の移り変わりです。")
        
        df = df.sort_values('timestamp')
        timeline_html = '<div class="timeline-container">'
        
        for index, row in df.iterrows():
            score = row['sentiment']
            stage = row.get('stage', 'その他')
            comment = row.get('comment', '')
            
            # クラス設定
            if score >= 0.1: m_cls, c_cls = "marker-pos", "border-pos"
            elif score <= -0.1: m_cls, c_cls = "marker-neg", "border-neg"
            else: m_cls, c_cls = "", ""
            
            plot_html = f"<div style='font-size:0.9rem;color:#555;margin-bottom:4px;font-style:italic;background:#f9f9f9;padding:4px;'>📖 (Fact) {html.escape(row.get('plot', ''))}</div>" if row.get('plot') else ""
            emotion_html = f"<div style='font-weight:bold;color:#333;'>💭 (Feeling) {html.escape(row.get('emotion_content', ''))}</div>"
            
            comment_html = ""
            if "API未設定" in comment or "AIエラー" in comment:
                reason_chips = ""
                if row.get('calc_log'):
                    for item in row['calc_log']:
                        if item.get('weight', 0) > 0:
                            cls = "chip-pos" if item['score'] > 0 else "chip-neg"
                            reason_chips += f"<span class='chip {cls}'>{html.escape(item['term'])} <b>{item['score']}</b></span>"
                        elif '逆接' in item.get('reason', ''):
                            reason_chips += f"<span class='chip' style='background:#fff3cd'>逆接 ➡ Boost</span>"
                
                comment_html = f"<div style='margin-top:8px;font-size:0.85rem;color:#666;border-top:1px dashed #ccc;padding-top:4px;'>📚 <b>辞書判定内訳:</b> {reason_chips}</div>" if reason_chips else f"<div style='margin-top:8px;font-size:0.85rem;color:#999;border-top:1px dashed #ccc;padding-top:4px;'>📚 辞書判定: 感情語なし</div>"
            else:
                comment_html = f"<div style='margin-top:8px;font-size:0.85rem;color:#666;border-top:1px dashed #ccc;padding-top:4px;line-height:1.4;'>🤖 <b>AI構造分析:</b> {html.escape(comment)}</div>"

            timeline_html += f"""<div class="timeline-item"><div class="timeline-time">{row['display_time']}</div><div class="timeline-marker {m_cls}"></div><div class="timeline-content {c_cls}"><div style="display:flex;justify-content:space-between;margin-bottom:8px;align-items:center;"><div><span class="stage-tag">{stage}</span></div><span style="font-size:0.8rem;font-weight:bold;color:#FF4B4B;">スコア: {score:+.2f}</span></div>{plot_html}{emotion_html}{comment_html}</div></div>"""
        
        timeline_html += '</div>'
        st.markdown(timeline_html, unsafe_allow_html=True)
    
    st.divider()
    st.subheader("💾 データ保存")
    col_dl1, col_dl2 = st.columns(2)
    safe_title = movie_title if movie_title else "Analysis"
    if st.session_state.notes:
        csv = df.to_csv(index=False).encode('utf-8-sig')
        col_dl1.download_button("📈 生データ (CSV)", csv, f'{safe_title}_data.csv', 'text/csv', use_container_width=True)
        html_log = generate_html_report(df, safe_title, st.session_state.characters).encode('utf-8')
        col_dl2.download_button("📄 レポート (HTML)", html_log, f'{safe_title}_report.html', 'text/html', use_container_width=True)
    
    # AI感想戦
    st.divider()
    st.subheader("🤖 AI構造分析チャット (Composite Analysis)")
    
    if st.session_state.gemini_api_key:
        if st.session_state.compare_data is not None:
            st.caption(f"現在の作品と『{st.session_state.compare_title}』を比較しながら、構造について議論できます。")
        else:
            st.caption("知識ベースに基づいて、AIが物語の構造について壁打ちを行います。")
        
        for chat in st.session_state.chat_history:
            with st.chat_message(chat["role"]): st.write(chat["content"])
            
        if prompt := st.chat_input("物語の構造についてAIと議論する..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.rerun() 

        if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
            last_prompt = st.session_state.chat_history[-1]["content"]
            with st.spinner("思考中..."):
                response = chat_with_ai(last_prompt)
                st.session_state.chat_history.append({"role": "assistant", "content": response})
                st.rerun()
    else:
        st.warning("⚠️ APIキーが設定されていないため、AIとの壁打ちチャット機能は無効化されています。サイドバーから設定してください。")