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
import altair as alt
from janome.tokenizer import Tokenizer

# モデル設定
MODEL_NAME = "gemini-2.5-flash-preview-09-2025"

# 安全性設定（物語分析でブロックされないように緩和）
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# =========================================================
# 0. アプリケーション設定 & CSS
# =========================================================
st.set_page_config(page_title="EmoTrace - Narrative & Emotion", layout="wide")

st.markdown("""
<style>
    /* ベースデザイン */
    body {
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
        background-color: #FDFDFD; color: #222;
    }
    h1 {
        color: #2C3E50;
        font-weight: 700; letter-spacing: -0.5px; margin-bottom: 0.5rem;
        border-bottom: 2px solid #eee; padding-bottom: 10px;
    }
    
    /* タイムライン表示 */
    .timeline-container { position: relative; padding: 20px 0; }
    .timeline-container::before { content: ''; position: absolute; top: 0; bottom: 0; left: 90px; width: 1px; background: #ddd; }
    
    .timeline-item { position: relative; margin-bottom: 24px; display: flex; align-items: flex-start; }
    .timeline-time { width: 80px; text-align: right; padding-right: 20px; font-family: 'Courier New', monospace; font-weight: bold; color: #666; font-size: 0.85rem; padding-top: 4px; }
    .timeline-marker { position: absolute; left: 86px; width: 9px; height: 9px; border-radius: 50%; background: #FFF; border: 2px solid #888; z-index: 1; margin-top: 6px; }
    .timeline-content { flex: 1; margin-left: 20px; background: #FFF; border-radius: 4px; padding: 12px 16px; border: 1px solid #eee; border-left-width: 4px; color: #333; }
    
    .marker-pos { border-color: #2a9d8f; background: #2a9d8f; } .border-pos { border-left-color: #2a9d8f; }
    .marker-neg { border-color: #e76f51; background: #e76f51; } .border-neg { border-left-color: #e76f51; }
    
    /* チャットエリア */
    .chat-container { border-top: 1px solid #eee; padding-top: 20px; margin-top: 30px; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 1. Janome & 辞書ロジック
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
                        if isinstance(val, (int, float)): score = float(val)
                        elif isinstance(val, str):
                            val = val.lower().strip()
                            if val in ['p', 'pos', 'positive']: score = 1.0
                            elif val in ['n', 'neg', 'negative']: score = -1.0
                            elif val in ['e', 'neu', 'neutral']: score = 0.0
                            else:
                                try: score = float(val)
                                except: pass
                        if score != 0.0: dic_data[term] = score
                    loaded_files.append(d['name'])
            except: pass
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
            if pos in ['名詞', '動詞', '形容詞', '副詞', '連体詞', '感動詞']:
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
# 2. ステート & AI知識ベース (詳細版復元)
# =========================================================

if 'status' not in st.session_state: st.session_state.status = 'ready'
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'elapsed_offset' not in st.session_state: st.session_state.elapsed_offset = 0.0
if 'notes' not in st.session_state: st.session_state.notes = [] 
if 'analyzed_notes' not in st.session_state: st.session_state.analyzed_notes = [] 
if 'gemini_api_key' not in st.session_state: st.session_state.gemini_api_key = ""
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'chat_initialized' not in st.session_state: st.session_state.chat_initialized = False
if 'compare_data' not in st.session_state: st.session_state.compare_data = None
if 'compare_title' not in st.session_state: st.session_state.compare_title = ""

# ユーザー提供の物語論を体系化した知識ベース (詳細版)
# AIの「脳内」にはこの知識を持たせるが、出力時は噛み砕かせる
KNOWLEDGE_BASE = """
【物語構造解析の理論的枠組み (AI参照用)】

1. **物語の基本遷移 (State Transition)**
   主人公は「初期状態」から「手段」を経て「帰結状態」へ移行する。
   * パターンA: プラス → マイナス (転落)
   * パターンB: マイナス → プラス (回復・成功)
   * パターンC: 無知 → 認識 (発見・覚醒)
   特に「マイナス→ゼロ（不遇からの脱却）」「ゼロ→プラス（獲得）」のパターンに注目。

2. **複合的構造モデル (Structural Models)**
   * **三幕構成**: 設定(Act1) → 対立/葛藤(Act2) → 解決(Act3)
   * **起承転結**: 導入 → 展開 → 転換/飛躍 → 結末
   * **行って帰る (Round Trip)**: 日常 → 境界越え → 異界での試練 → 帰還（変化した日常）

3. **現代的な訴求パターン (Modern Appeal)**
   * 問題解決: 直面する問題への有効な解決策の提示。
   * ゴール到達: 目的への道筋。
   * 価値観の揺さぶり: 異質な価値観との衝突と変容。

4. **時間とリズムの技法 (Time & Rhythm)**
   物語の「語り」のリズムを決定する4つの描写法。
   * **省略法 (Ellipsis)**: 書かないことによる時間の跳躍。スピードアップ。
   * **要約法 (Summary)**: 長い時間を短く説明する。つなぎ。
   * **情景法 (Scene)**: 会話など、リアルタイムに近い描写。重要シーン。
   * **描写的休止法 (Pause)**: 時間を止めて詳細に描写する。感情の深化、タメ。

5. **叙法と焦点化 (Focalization)**
   * **内的焦点化**: 特定の人物の五感・思考に限定する（感情移入）。
   * **外的焦点化**: 客観的なカメラの視点。内面を描かない。
"""

# 対話用プロンプト：知識ある友人のトーン
WALL_PARTNER_PROMPT = f"""
あなたは、ユーザーと一緒に作品の構造や演出の面白さを深掘りする「知的なパートナー」です。
ユーザーの鑑賞ログをもとに、気づきを与えるような対話を行ってください。

【あなたのスタンス：50の塩梅】
* **口調**: 「です・ます」調の丁寧語ですが、堅苦しくなりすぎないように。「〜ですね」「〜だと思います」といった、**対話的な柔らかさ**を持ってください。
    * NG（堅すぎ）: 「拝察いたします」「示唆されています」「推測されます」「克明に」
    * NG（崩しすぎ）: 「マジで」「〜じゃん」「ウケる」
    * OK（理想）: 「〜のように見えますね」「〜という意図がありそうです」「ここは面白いですね」
* **知識の出し方**: 専門用語（Act、ミッドポイント等）は使わず、**「物語の折り返し」「タメ」「急展開」**などの平易な言葉で説明してください。
* **姿勢**: ユーザーを「観察対象」として記述するのではなく、**「体験を共有した相手」**として話しかけてください。一方的に教えるのではなく、「こういう見方もできそうですね」と視点を広げる手伝いをします。

【対話のガイドライン】
1.  **事実と感情のつながり**: 「状況は大変なのに、楽しんでいるのが面白いですね。演出がコミカルだからでしょうか？」のように、ログから読み取れる矛盾や特徴を話題にします。
2.  **リズムの話**: 「ここで急に展開が早くなりましたね」「じっくり描いているのが印象的です」など、ペース配分について触れます。
3.  **不足情報の確認**: 音楽や色彩など、ログにない情報が分析に必要なら、「この時、どんな音がしていましたか？」と自然に聞いてください。
4.  **問いかけ**: 最後に、ユーザーが自分の言葉で語りたくなるような、シンプルな問いを投げかけてください。

【知識ベース（参照用）】
{KNOWLEDGE_BASE}
"""

# =========================================================
# 3. 分析・ヘルパー関数
# =========================================================

def generate_with_retry(model, contents, config=None):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # safety_settingsを常に適用
            return model.generate_content(
                contents, 
                generation_config=config,
                safety_settings=SAFETY_SETTINGS
            )
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                time.sleep(2 ** attempt + 1)
                continue
            raise e

def get_safe_text(response):
    try:
        return response.text
    except Exception:
        try:
            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content.parts:
                    return candidate.content.parts[0].text
        except Exception:
            pass
    return ""

def analyze_scene_with_ai(plot_text, emotion_text):
    # 辞書判定
    dict_score, calc_log = analyze_sentiment_advanced(emotion_text)
    dict_info = f"辞書スコア:{dict_score:.2f}"
    
    api_key = st.session_state.gemini_api_key
    if not api_key:
        return dict_score, 0.0, "API未設定", "", calc_log, dict_score

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        
        prompt = f"""
        物語のワンシーンを分析し、JSONを生成してください。
        
        【入力】
        Plot: {plot_text} (出来事)
        Feeling: {emotion_text} (ユーザーの気持ち)
        DictData: {dict_info}
        
        【知識ベース (参照用)】
        {KNOWLEDGE_BASE}
        
        【指示】
        以下の要素を出力してください。専門用語は使わず、**丁寧だが堅苦しくない言葉**で。
        
        1. **story_score**: 客観的な状況の良し悪し（成功/失敗, 安全/ピンチ）。
        2. **user_score**: あなたの主観（楽しい/つまらない）。Feelingを最優先。
        3. **reason**: 
           - この場面のスコアの理由を、**話しかけるような口調**で短く説明してください。
           - 「示唆する」などの論文調や、「～だぜ」などの乱暴な言葉は禁止。
           - 例：「ピンチの場面ですが、ワクワクする展開なのでプラスです。」
        
        Output JSON format:
        {{ "story_score": float, "user_score": float, "reason": string }}
        """
        
        response = generate_with_retry(model, prompt, config={"response_mime_type": "application/json"})
        text_content = get_safe_text(response).strip()
        text_content = text_content.replace('```json', '').replace('```', '')
        
        if not text_content:
             return dict_score, 0.0, "AI応答なし", "", calc_log, dict_score

        match = re.search(r'\{.*\}', text_content, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return (
                float(result.get("user_score", dict_score)),
                float(result.get("story_score", 0.0)),
                result.get("reason", ""),
                calc_log,
                dict_score
            )
        else:
            return dict_score, 0.0, "解析エラー", "", calc_log, dict_score

    except Exception as e:
        return dict_score, 0.0, f"エラー: {str(e)[:20]}", "", calc_log, dict_score

def generate_initial_structural_analysis(notes):
    """
    全ログ終了後、物語全体の構造を分析し、ユーザーへの最初の問いかけを生成する
    """
    api_key = st.session_state.gemini_api_key
    if not api_key: return "APIキーを設定してください。"
    
    # ログをテキスト化
    story_log = ""
    for n in notes:
        story_log += f"- [{n['display_time']}] Plot:{n['plot']} / Feeling:{n['emotion_content']} (UserScore:{n['sentiment']:.2f}, StoryScore:{n.get('story_score',0):.2f})\n"
    
    prompt = f"""
    以下はユーザーが記録した物語の鑑賞ログです。**これが物語の全容であり、ここで完結しています。**
    `KNOWLEDGE_BASE` の理論に基づきつつ、**ラジオのパーソナリティのような、知的で聞きやすい語り口**で振り返りを作成してください。

    【ログ】
    {story_log}

    【トーン＆マナー：50の塩梅】
    * **禁止ワード**: 「拝見」「拝察」「克明」「一気呵成」「牽引」「収束」「～と思われる」「～である」「鑑賞者」。
    * **推奨ワード**: 「～ですね」「～かもしれません」「～という印象です」。
    * **姿勢**: ユーザーを「被験者」のように分析するのではなく、**「体験を共有した相手」**として「あなた」と呼びかけてください。

    【出力フォーマット】
    
    ## 🎬 鑑賞体験の振り返り
    
    **1. 感情の動き**
    （専門的な分析を裏側に持ちつつ、感情がどう動いたかを「波」や「山」のイメージで分かりやすく説明してください）
    
    **2. 状況と感情の面白さ**
    （PlotとFeelingにギャップがある場所や、ぴったり合っている場所について、「ここが面白いですね」という視点で触れてください）
    
    **3. 物語のリズム**
    （展開のスピードや、時間の使い方について。細かい秒数には触れず、感覚的な速さについて話してください）

    ---
    **🤖 考えるヒント**
    （もし分析に足りない情報があれば質問してください。なければ、結末の演出やテーマについて、ユーザーが答えやすい問いを一つだけ投げかけてください）
    """
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        response = generate_with_retry(model, prompt)
        text = get_safe_text(response)
        if not text:
            # フォールバックメッセージ
            return "物語の構造分析を行おうとしましたが、応答の生成に失敗しました。チャット欄で、気になったシーンについて話しかけてみてください。"
        return text
    except Exception as e:
        return f"構造分析エラー: {str(e)}"

def chat_with_ai(user_message):
    api_key = st.session_state.gemini_api_key
    if not api_key: return "APIキーを設定してください。"
    
    history = []
    # 直近の分析ログをコンテキストに追加
    if st.session_state.analyzed_notes:
        notes_context = "【参照用: 直近のシーンログ】\n"
        for note in st.session_state.analyzed_notes[-5:]: 
            notes_context += f"- Time:{note['display_time']} / Plot:{note['plot']} / Feeling:{note['emotion_content']} (UserScore:{note['sentiment']:.2f}, StoryScore:{note.get('story_score',0):.2f})\n"
        history.append({"role": "user", "parts": [notes_context]})
    
    # チャット履歴
    for msg in st.session_state.chat_history:
        role = "user" if msg["role"] == "user" else "model"
        history.append({"role": role, "parts": [msg["content"]]})
    
    history.append({"role": "user", "parts": [user_message]})
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=WALL_PARTNER_PROMPT)
        response = generate_with_retry(model, history)
        return get_safe_text(response)
    except Exception as e:
        return f"通信エラー: {str(e)}"

def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def calculate_decay_curve(df_notes, duration, target_col='sentiment'):
    max_time = int(duration) + 1
    decay_scores = np.zeros(max_time)
    
    events = {}
    for _, row in df_notes.iterrows():
        t_idx = int(row['timestamp'])
        if t_idx < max_time:
            events[t_idx] = row.get(target_col, 0.0)
            
    LIFETIME = 60.0
    last_t = -999
    last_s = 0.0
    
    for t in range(max_time):
        if t in events:
            decay_scores[t] = events[t]
            last_t = t
            last_s = events[t]
        elif last_t != -999:
            delta = t - last_t
            if delta < LIFETIME:
                decay_scores[t] = last_s * math.cos((math.pi/2)*(delta/LIFETIME))
            else:
                decay_scores[t] = 0.0
                last_t = -999
                last_s = 0.0
                
    return pd.DataFrame({'timestamp': np.arange(max_time), 'score': decay_scores})

def generate_html_report(df, title):
    rows_html = ""
    for _, row in df.sort_values('timestamp').iterrows():
        score = row['sentiment']
        
        border_color = '#2a9d8f' if score >= 0.1 else '#e76f51' if score <= -0.1 else '#ccc'
        
        # 安全な文字列取得
        plot_txt = str(row.get('plot', '')) if pd.notna(row.get('plot', '')) else ''
        emo_txt = str(row.get('emotion_content', '')) if pd.notna(row.get('emotion_content', '')) else ''
        comment_txt = str(row.get('comment', '')) if pd.notna(row.get('comment', '')) else ''
        
        rows_html += f"""
        <div style="border-left:4px solid {border_color}; background:#fff; padding:12px; margin-bottom:12px; border-radius:4px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
            <div style="font-size:0.85em; color:#666; font-family:monospace; margin-bottom:4px; display:flex; justify-content:space-between;">
                <span>{row['display_time']}</span>
                <strong style="color:#555;">User: {score:+.2f} / Story: {row.get('story_score', 0):+.2f}</strong>
            </div>
            <div style="margin-bottom:6px;">
                <span style="font-weight:bold; color:#333;">{html.escape(plot_txt)}</span>
            </div>
            <div style="font-size:0.9em; color:#555;">
                💭 {html.escape(emo_txt)}
            </div>
            <div style="margin-top:8px; font-size:0.85em; color:#444; border-top:1px dashed #eee; padding-top:4px;">
                🤖 {html.escape(comment_txt)}
            </div>
        </div>"""
    
    return f"<html><body style='font-family:sans-serif;padding:20px;background:#f9f9f9;'><h2>{html.escape(title)} Analysis Report</h2>{rows_html}</body></html>"

# =========================================================
# 4. メインUI
# =========================================================
with st.sidebar:
    st.header("⚙️ 設定")
    api_key_input = st.text_input("Gemini API Key", type="password", value=st.session_state.gemini_api_key)
    if api_key_input: st.session_state.gemini_api_key = api_key_input
    
    st.divider()
    
    # 復元機能の追加
    with st.expander("📂 データの読み込み (復元)"):
        uploaded_restore = st.file_uploader("過去のログ(CSV)", type=["csv"], key="restore_csv")
        if uploaded_restore:
            try:
                df_restore = pd.read_csv(uploaded_restore)
                if st.button("このデータを復元して分析"):
                    # データを辞書リストに変換
                    restored_notes = df_restore.to_dict('records')
                    st.session_state.notes = restored_notes
                    st.session_state.analyzed_notes = restored_notes
                    
                    # 状態を分析完了に
                    st.session_state.status = 'finished'
                    
                    # 時間を末尾に合わせる
                    if not df_restore.empty:
                        st.session_state.elapsed_offset = float(df_restore['timestamp'].max())
                    
                    # チャット履歴はリセット
                    st.session_state.chat_history = []
                    
                    # APIキーがあれば初期分析を生成
                    if st.session_state.gemini_api_key:
                        with st.spinner("データを読み込み、構造を分析中..."):
                            initial_msg = generate_initial_structural_analysis(restored_notes)
                            st.session_state.chat_history.append({"role": "model", "content": initial_msg})
                            st.session_state.chat_initialized = True
                    
                    st.success("データを復元しました。")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"読み込みエラー: {e}")

    with st.expander("📂 過去データの比較"):
        uploaded_file = st.file_uploader("CSVファイル", type=["csv"], key="compare_csv")
        if uploaded_file:
            try:
                compare_df = pd.read_csv(uploaded_file)
                st.session_state.compare_data = compare_df
                st.session_state.compare_title = uploaded_file.name
                st.success(f"『{st.session_state.compare_title}』読込完了")
            except: st.error("読込エラー")
        if st.button("比較クリア"):
            st.session_state.compare_data = None
            st.session_state.compare_title = ""
            st.rerun()

    st.divider()
    if st.button("🗑️ 新規作成 (リセット)", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

st.title("EmoTrace - Narrative Analysis")
st.caption("あらゆる物語の構造と感情の揺れ動きを分析し、体験を言語化するツール")

work_title = st.text_input("作品名", placeholder="作品名を入力", label_visibility="collapsed")

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
    # 終了・分析トリガー
    if st.button("■ 終了・構造分析へ", type="secondary", use_container_width=True, disabled=(st.session_state.status == 'ready')):
        if st.session_state.status == 'playing': st.session_state.elapsed_offset += time.time() - st.session_state.start_time
        st.session_state.status = 'finished'
        
        if st.session_state.notes:
            progress = st.progress(0)
            status_txt = st.empty()
            analyzed_data = []
            
            total = len(st.session_state.notes)
            for i, note in enumerate(st.session_state.notes):
                status_txt.text(f"シーン解析中... ({i+1}/{total})")
                if i > 0: time.sleep(0.5) # レート制限対策で少し待機
                
                user_sc, story_sc, rsn, log, dict_sc = analyze_scene_with_ai(note['plot'], note['emotion_content'])
                new_note = note.copy()
                new_note.update({
                    "sentiment": user_sc, 
                    "story_score": story_sc,
                    "comment": rsn, 
                    "calc_log": log, "dictionary_score": dict_sc 
                })
                analyzed_data.append(new_note)
                progress.progress((i + 1) / total)
            
            st.session_state.analyzed_notes = analyzed_data
            
            # 全体構造分析の生成
            if st.session_state.gemini_api_key:
                status_txt.text("物語全体の構造を構築中...")
                initial_msg = generate_initial_structural_analysis(analyzed_data)
                st.session_state.chat_history.append({"role": "model", "content": initial_msg})
                st.session_state.chat_initialized = True

            status_txt.empty()
            progress.empty()
            st.toast("分析完了。物語の構造を紐解きます。", icon="📝")
        
        st.rerun()

# 入力フォーム
if st.session_state.status in ['playing', 'paused']:
    st.divider()
    with st.form("log_form", clear_on_submit=True):
        c_plot, c_emo = st.columns(2)
        plot = c_plot.text_area("📖 プロット (事実・出来事)", height=80, placeholder="例: 主人公がライバルに敗北した。雨が降り始めた。")
        emo = c_emo.text_area("💭 感情・印象 (感覚)", height=80, placeholder="例: 悔しい。画面が暗くて重苦しい。時間が長く感じた。")
        
        if st.form_submit_button("記録", type="primary", use_container_width=True):
            if plot or emo:
                ts = current_time
                st.session_state.notes.append({
                    "timestamp": ts, "display_time": format_time(ts),
                    "plot": plot, "emotion_content": emo
                })
                st.toast("ログを記録しました")
                
    # 記録済みログの編集機能 (追加)
    if st.session_state.notes:
        with st.expander("📝 記録済みログの確認・編集", expanded=False):
            # インデックスを逆順にして新しいものを上に
            for i in range(len(st.session_state.notes) - 1, -1, -1):
                note = st.session_state.notes[i]
                c_del, c_edit = st.columns([1, 6])
                
                with c_del:
                    st.write(f"No.{i+1}")
                    if st.button("削除", key=f"del_{i}", use_container_width=True):
                        st.session_state.notes.pop(i)
                        st.rerun()
                
                with c_edit:
                    c1, c2 = st.columns(2)
                    new_plot = c1.text_area(f"[{note['display_time']}] プロット", value=note['plot'], key=f"p_{i}", height=70)
                    new_emo = c2.text_area("感情・印象", value=note['emotion_content'], key=f"e_{i}", height=70)
                    
                    # 変更を即時反映
                    if new_plot != note['plot']:
                        st.session_state.notes[i]['plot'] = new_plot
                    if new_emo != note['emotion_content']:
                        st.session_state.notes[i]['emotion_content'] = new_emo
                st.divider()

# 分析結果表示
if st.session_state.status == 'finished':
    st.divider()
    st.header("📊 Narrative Structure & Rhythm")
    
    if st.session_state.analyzed_notes:
        df = pd.DataFrame(st.session_state.analyzed_notes)
        max_time = max(df['timestamp'].max(), 60)
        
        # 1. 感情曲線 (物語 vs 感情)
        st.subheader("1. 感情体験と物語の雰囲気")
        st.info("💡 緑の実線: あなたの感情スコア / 青の点線: 物語の状況スコア (客観)")
        
        # ユーザー感情の減衰曲線
        df_user = calculate_decay_curve(df, max_time, target_col='sentiment')
        df_user['Type'] = 'User Sentiment'
        
        # 物語雰囲気の減衰曲線
        df_story = calculate_decay_curve(df, max_time, target_col='story_score')
        df_story['Type'] = 'Story Tone'
        
        # データ結合
        df_chart_all = pd.concat([df_user, df_story])
        df_chart_all['Minutes'] = df_chart_all['timestamp'] / 60
        
        # Altairチャート
        base = alt.Chart(df_chart_all).encode(
            x=alt.X('Minutes', title='経過時間 (分)'),
            y=alt.Y('score', title='スコア', scale=alt.Scale(domain=[-1.2, 1.2])),
            tooltip=['Minutes', 'score', 'Type']
        ).properties(height=350)
        
        # ユーザー感情線 (実線, 緑)
        line_user = base.transform_filter(
            alt.datum.Type == 'User Sentiment'
        ).mark_line(color='#2a9d8f', size=3)
        
        # 物語雰囲気線 (点線, 青)
        line_story = base.transform_filter(
            alt.datum.Type == 'Story Tone'
        ).mark_line(color='#2c3e50', strokeDash=[4, 4], size=2, opacity=0.7)
        
        # 過去データ比較があれば追加
        layers = [line_story, line_user]
        
        if st.session_state.compare_data is not None:
            max_t_comp = st.session_state.compare_data['timestamp'].max()
            df_comp_decay = calculate_decay_curve(st.session_state.compare_data, max(max_time, max_t_comp), target_col='sentiment')
            df_comp_decay['Minutes'] = df_comp_decay['timestamp'] / 60
            
            comp_line = alt.Chart(df_comp_decay).mark_line(color='#aaa', strokeDash=[2,2]).encode(
                x='Minutes',
                y='score',
                tooltip=[alt.Tooltip('score', title='Compare Score')]
            )
            layers.insert(0, comp_line) # 最背面に

        st.altair_chart(alt.layer(*layers).interactive(), use_container_width=True)

        # 2. タイムライン
        st.subheader("2. シーン詳細と構造解析")
        tl_html = '<div class="timeline-container">'
        for _, row in df.sort_values('timestamp').iterrows():
            sc = row['sentiment']
            ssc = row.get('story_score', 0.0)
            
            # ユーザー感情による色分け
            cls = "marker-pos" if sc > 0.1 else "marker-neg" if sc < -0.1 else ""
            b_cls = "border-pos" if sc > 0.1 else "border-neg" if sc < -0.1 else ""
            
            # 物語スコアの表示色
            ssc_color = "#2a9d8f" if ssc > 0.1 else "#e76f51" if ssc < -0.1 else "#999"
            
            # 安全な文字列取得（NaN対策）
            plot_txt = str(row.get('plot', '')) if pd.notna(row.get('plot', '')) else ''
            emo_txt = str(row.get('emotion_content', '')) if pd.notna(row.get('emotion_content', '')) else ''
            comment_txt = str(row.get('comment', '')) if pd.notna(row.get('comment', '')) else ''
            
            tl_html += f"""
            <div class="timeline-item">
                <div class="timeline-time">{row['display_time']}</div>
                <div class="timeline-marker {cls}"></div>
                <div class="timeline-content {b_cls}">
                    <div style="display:flex; justify-content:flex-end; align-items:center; margin-bottom:4px; font-size:0.8em; color:#666;">
                        <span style="margin-right:10px;">Story: <strong style="color:{ssc_color};">{ssc:+.2f}</strong></span>
                        <span>User: <strong>{sc:+.2f}</strong></span>
                    </div>
                    <div style="font-size:0.95em; font-weight:bold; margin-bottom:4px;">{html.escape(plot_txt)}</div>
                    <div style="font-size:0.9em; color:#666; font-style:italic; margin-bottom:8px;">💭 {html.escape(emo_txt)}</div>
                    <div style="font-size:0.85em; color:#333; background:#f9f9f9; padding:6px; border-radius:4px;">
                        🤖 {html.escape(comment_txt)}
                    </div>
                </div>
            </div>"""
        st.markdown(tl_html + '</div>', unsafe_allow_html=True)
        
        # ダウンロード
        csv = df.to_csv(index=False).encode('utf-8-sig')
        html_rep = generate_html_report(df, work_title if work_title else "Analysis").encode('utf-8')
        c_d1, c_d2 = st.columns(2)
        c_d1.download_button("CSV保存", csv, "log.csv", "text/csv")
        c_d2.download_button("レポート保存", html_rep, "report.html", "text/html")

    # 3. 構造分析チャット
    st.divider()
    st.subheader("🧬 構造分析・深掘り (Structural Analysis)")
    
    if st.session_state.gemini_api_key:
        # チャット履歴表示
        for chat in st.session_state.chat_history:
            role = "user" if chat["role"] == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(chat["content"])
        
        # 入力欄
        if prompt := st.chat_input("分析に対する考察や、自身の解釈を入力..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.rerun()
            
        # AI応答生成
        if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
            with st.spinner("考察を深めています..."):
                resp = chat_with_ai(st.session_state.chat_history[-1]["content"])
                st.session_state.chat_history.append({"role": "model", "content": resp})
                st.rerun()
    else:
        st.info("APIキーを設定すると、AIによる構造分析と壁打ちが可能になります。")