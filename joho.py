import streamlit as st
import pandas as pd
import numpy as np
import time
from janome.tokenizer import Tokenizer
import os
import re
import streamlit.components.v1 as components
import math
import html
import google.generativeai as genai
import json

# =========================================================
# 0. アプリケーション設定 & CSS
# =========================================================
st.set_page_config(page_title="CineLog - 映画分析", layout="wide")

st.markdown("""
<style>
    /* ベースフォント設定 */
    body {
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
        background-color: #FAFAFA; color: #333;
    }
    /* アプリタイトル */
    h1 {
        background: linear-gradient(45deg, #FF4B4B, #FF914D);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-weight: 800; letter-spacing: -1px; margin-bottom: 0.5rem;
    }
    /* タイマー */
    [data-testid="stMetricValue"] {
        font-family: 'Courier New', Courier, monospace;
        font-weight: bold; font-size: 3rem !important;
        color: #444; text-shadow: 2px 2px 0px rgba(0,0,0,0.1);
    }
    /* ボタン */
    .stButton > button {
        border-radius: 12px; font-weight: 600; border: none;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1); padding: 0.5rem 1rem;
    }
    .stButton > button:hover {
        transform: translateY(-2px) scale(1.02); box-shadow: 0 10px 20px rgba(0,0,0,0.1);
    }
    .stButton > button:active { transform: translateY(1px); }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #FF4B4B 0%, #FF6B6B 100%); border: none;
    }
    /* テキストエリア */
    .stTextArea textarea {
        border-radius: 12px; border: 1px solid #E0E0E0;
        background-color: #FFF !important; color: #333 !important;
        font-size: 16px; line-height: 1.6; padding: 16px;
        transition: all 0.3s ease; box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
    }
    .stTextArea textarea:focus {
        border-color: #FF4B4B; box-shadow: 0 0 0 3px rgba(255, 75, 75, 0.15);
    }
    /* タイムライン */
    .timeline-container { position: relative; padding: 20px 0; }
    .timeline-container::before { content: ''; position: absolute; top: 0; bottom: 0; left: 80px; width: 2px; background: #E0E0E0; }
    .timeline-item { position: relative; margin-bottom: 24px; display: flex; align-items: flex-start; }
    .timeline-time { width: 70px; text-align: right; padding-right: 20px; font-family: 'Courier New', monospace; font-weight: bold; color: #888; font-size: 0.9rem; padding-top: 4px; }
    .timeline-marker { position: absolute; left: 74px; width: 14px; height: 14px; border-radius: 50%; background: #FFF; border: 3px solid #ccc; z-index: 1; margin-top: 5px; }
    .timeline-content { flex: 1; margin-left: 30px; background: #FFF; border-radius: 12px; padding: 16px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-left: 5px solid #ccc; transition: transform 0.2s; color: #333; }
    .timeline-content:hover { transform: translateX(4px); box-shadow: 0 6px 15px rgba(0,0,0,0.08); }
    
    /* 感情値による色分け */
    .marker-pos { border-color: #FF914D; } .border-pos { border-left-color: #FF914D; } .score-pos { color: #FF914D; }
    .marker-neg { border-color: #4D91FF; } .border-neg { border-left-color: #4D91FF; } .score-neg { color: #4D91FF; }
    .marker-mark { border-color: #FFD700; background: #FFD700; } .border-mark { border-left-color: #FFD700; background-color: #FFFCF0; }
    
    /* キャラクターカード */
    .char-card {
        background: white; border-radius: 12px; padding: 15px; margin-bottom: 15px;
        border: 1px solid #eee; box-shadow: 0 2px 5px rgba(0,0,0,0.03); display: flex; align-items: flex-start;
    }
    .char-icon {
        font-size: 1.5rem; margin-right: 15px; background: #f0f2f6; border-radius: 50%;
        width: 40px; height: 40px; display: flex; justify-content: center; align-items: center;
    }
    .char-info { flex: 1; }
    .char-name { font-weight: bold; font-size: 1.1rem; color: #333; margin-bottom: 4px; }
    .char-desc { font-size: 0.9rem; color: #666; white-space: pre-wrap; line-height: 1.5; }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .block-container { animation: fadeIn 0.6s ease-out forwards; }
</style>
""", unsafe_allow_html=True)


# =========================================================
# 1. ステート管理
# =========================================================
if 'status' not in st.session_state: st.session_state.status = 'ready'
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'elapsed_offset' not in st.session_state: st.session_state.elapsed_offset = 0.0
if 'notes' not in st.session_state: st.session_state.notes = []
if 'custom_categories' not in st.session_state: st.session_state.custom_categories = []
if 'characters' not in st.session_state: st.session_state.characters = [] 
if 'sentiment_dict' not in st.session_state: st.session_state.sentiment_dict = None
if 'gemini_api_key' not in st.session_state: st.session_state.gemini_api_key = ""
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'chat_initialized' not in st.session_state: st.session_state.chat_initialized = False
if 'chat_mode' not in st.session_state: st.session_state.chat_mode = "詳細分析"

# チャットリセット用関数（モード切替時に呼ぶ）
def reset_chat():
    st.session_state.chat_history = []
    st.session_state.chat_initialized = False


# =========================================================
# 2. NLPルール定義
# =========================================================
NEGATION_WORDS = ['ない', 'ず', 'ぬ', 'まい']
ADVERSATIVE_WORDS = ['しかし', 'でも', 'だが', 'ところが', 'けど', 'けれど', 'けれども']
COMPOUND_RULES = {
    ('値段', '高い'): -1.0, ('敷居', '高い'): -1.0, ('プライド', '高い'): -0.8,
    ('腰', '重い'): -0.8, ('口', '軽い'): -0.8, ('目', 'ない'): 1.0,
    ('音沙汰', 'ない'): -1.0, ('飽き', 'こない'): 1.0, ('テンション', '高い'): 1.0,
    ('器', '大きい'): 1.0, ('コストパフォーマンス', '高い'): 1.0,
    ('コスパ', '高い'): 1.0, ('気', '強い'): -0.5,
    ('いい', '感じ'): 1.0, ('良い', '感じ'): 1.0, ('よい', '感じ'): 1.0,
}

@st.cache_resource
def load_sentiment_dictionary():
    candidates = [os.path.join('dic', 'pn_ja.dic'), 'pn_ja.dic']
    dic_lemma = {}
    loaded = False
    for path in candidates:
        if os.path.exists(path):
            try:
                df_pn = pd.read_csv(path, encoding="sjis", sep=":", names=["lemma", "reading", "pos", "score"], header=None)
                dic_lemma = df_pn.set_index('lemma')['score'].to_dict()
                loaded = True
                break
            except Exception: pass
    return dic_lemma, loaded

@st.cache_resource
def get_tokenizer():
    return Tokenizer()

sentiment_dict, is_dict_loaded = load_sentiment_dictionary()


# =========================================================
# 3. 感情分析エンジン
# =========================================================
def refine_sentiment_with_gemini(text, dict_score):
    api_key = st.session_state.gemini_api_key
    if not api_key: return dict_score, ""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"""
        あなたは映画評論の感情分析エキスパートです。以下の鑑賞メモの感情を-1.0〜1.0で数値化し理由を述べて。
        辞書判定値: {dict_score}
        回答はJSON形式のみ: {{ "score": 数値, "reason": "判定理由（20文字以内）" }}
        メモ: {text}
        """
        response = model.generate_content(prompt)
        match = re.search(r'\{.*\}', response.text.strip(), re.DOTALL)
        if match:
            data = json.loads(match.group())
            return max(-1.0, min(1.0, float(data.get("score", dict_score)))), data.get("reason", "AI文脈判断")
        else: return dict_score, "AI解析エラー"
    except Exception as e: return dict_score, f"AIエラー: {str(e)}"

def analyze_sentiment_advanced(text):
    if not text: return 0.0, []
    text_norm = text.replace("ありません", "ないです")
    t = get_tokenizer()
    tokens = list(t.tokenize(text_norm))
    matched_scores = []
    calc_log = []
    target_pos = ['名詞', '動詞', '形容詞', '副詞']
    current_boost = 1.0 
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        base_form = token.base_form
        pos = token.part_of_speech.split(',')[0]
        sub_pos = token.part_of_speech.split(',')[1]
        
        is_adversative = False
        if pos == '接続詞' and base_form in ADVERSATIVE_WORDS: is_adversative = True
        elif pos == '助詞' and sub_pos == '接続助詞' and base_form in ['が', 'けど', 'けれど', 'けれども']: is_adversative = True
        if is_adversative: current_boost = 1.5
        
        current_score = 0.0
        original_score = 0.0
        found_sentiment = False
        matched_term = base_form
        reason = ""
        
        if pos in ['形容詞', '動詞', '名詞']:
            for j in range(1, 5): 
                if i - j >= 0:
                    prev_token = tokens[i-j]
                    prev_base = prev_token.base_form
                    if (prev_base, base_form) in COMPOUND_RULES:
                        current_score = COMPOUND_RULES[(prev_base, base_form)]
                        original_score = current_score
                        found_sentiment = True
                        matched_term = f"{prev_base} + {base_form}"
                        reason = "連語ルール"; break
        
        if not found_sentiment:
            if pos in target_pos and base_form in sentiment_dict:
                raw_score = sentiment_dict[base_form]
                original_score = raw_score
                current_score = raw_score
                found_sentiment = True
                reason = "辞書マッチ"
        
        if found_sentiment:
            negated = False
            negation_term = ""
            for k in range(1, 4):
                if i + k < len(tokens):
                    next_token = tokens[i+k]
                    next_base = next_token.base_form
                    next_pos = next_token.part_of_speech.split(',')[0]
                    if next_base in NEGATION_WORDS: negated = True; negation_term = next_base; break
                    if next_base in ['。', '、', '！', '？', '!?', 'EOS']: break
                    if next_pos in ['名詞', '動詞', '形容詞'] and next_base not in ['する', 'なる']: break
            if negated:
                current_score *= -1.0
                reason += f" ➡ 否定「{negation_term}」"
            matched_scores.append(current_score)
            log_reason = reason + (" [逆接後]" if current_boost > 1.0 else "")
            calc_log.append({'term': matched_term, 'score': current_score, 'original_score': original_score, 'reason': log_reason, 'boost_factor': current_boost})
        i += 1

    count = len(matched_scores)
    if count == 0: dict_score = 0.0
    else:
        weighted_sum = 0.0
        total_weight = 0.0
        for idx, item in enumerate(calc_log):
            score = matched_scores[idx]
            base_weight = 1.0
            final_weight = base_weight * item['boost_factor']
            weighted_sum += score * final_weight
            total_weight += final_weight
            item['weight'] = final_weight
        dict_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    final_score = dict_score
    if st.session_state.gemini_api_key and len(text) > 2:
        ai_score, ai_reason = refine_sentiment_with_gemini(text, dict_score)
        if abs(ai_score - dict_score) > 0.01:
            calc_log.append({'term': '🤖 AI補正', 'score': ai_score, 'original_score': dict_score, 'reason': ai_reason, 'boost_factor': 1.0, 'weight': 1.0})
            final_score = ai_score
    
    return max(-1.0, min(1.0, final_score)), calc_log


# =========================================================
# 4. 感想戦（チャット）機能
# =========================================================

# 【詳細分析モード用】物語を深く掘り下げるための質問リスト
KNOWLEDGE_DETAILED = """
【詳細分析モード：物語構造の深堀り】
以下の14の視点に基づき、ユーザーのメモから関連する要素を深く掘り下げてください。
1. プロットの核（一言でいうと？）
2. 主人公：欠落・象徴（冒頭で何が欠けていたか）
3. 主人公の現在位置（運命自覚前、成功、低迷、失敗のどれか）
4. 主人公の過去（現在を形作ったもの）
5. クエストと目的（具体的なミッションは何か）
6. 象徴的に得る（or 失う）もの
7. 敵対者（アンタゴニスト：価値観の違い）
8. 協力者（味方：なぜ助けるのか）
9. 日常世界（冒頭の環境と迫る危機）
10. 変化を促す存在（使者、依頼者）
11. 旅の最深部（日常から最も遠い場所での試練）
12. 喪失（目的達成の代償）
13. 敵対者との最終局面（対峙、理解、和解あるいは決裂）
14. 結末（環境の変化、欠落は埋まったか）
"""

# 【簡易分析モード用】あらかた掴むための質問リスト
KNOWLEDGE_SIMPLE = """
【簡易分析モード：物語の骨格把握】
以下の3つの主要点に絞って、物語の全体像を整理する手助けをしてください。
1. 物語の核（結局、誰が何をする話だったのか）
2. 主人公の目的と動機（何のために戦っていたのか）
3. 結末と変化（最初と最後で何が変わったか）
"""

def init_chat_with_analysis(df_notes):
    api_key = st.session_state.gemini_api_key
    if not api_key:
        st.session_state.chat_history.append({"role": "assistant", "content": "分析お疲れ様でした！APIキーを設定すると、AIとの感想戦ができます。"})
        return

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        logs_text = ""
        for _, row in df_notes.iterrows():
            logs_text += f"- {row['display_time']} [{row['category']}]: {row['content']} (感情値:{row['sentiment']:.2f})\n"

        mode = st.session_state.chat_mode
        knowledge = KNOWLEDGE_DETAILED if mode == "詳細分析" else KNOWLEDGE_SIMPLE

        prompt = f"""
        あなたは映画分析のプロフェッショナルメンターです。
        ユーザーの鑑賞ログをもとに、選択されたモード「{mode}」に従って深掘り質問をしてください。

        【知識ベース】
        {knowledge}

        【鑑賞ログ】
        {logs_text}

        【指示】
        1. ログの中で感情値が高いシーンや見返しマークがある箇所に着目してください。
        2. 知識ベースの中から、そのシーンに関連する問いを選んで質問してください。（一度に聞くのは1つか2つまで）
        3. 語り口は丁寧かつフレンドリーな映画好きのトーンで。
        4. 質問の後に、必ず【現時点でのストーリー骨格】というセクションを設け、これまでの情報から推測される物語の構造を箇条書きで要約してください。（初回なので推測で構いません）
        """
        response = model.generate_content(prompt)
        st.session_state.chat_history.append({"role": "assistant", "content": response.text.strip()})
        st.session_state.chat_initialized = True
    except Exception as e:
        st.session_state.chat_history.append({"role": "assistant", "content": f"AI接続エラー: {str(e)}"})

def process_chat_input(user_input):
    api_key = st.session_state.gemini_api_key
    if not api_key: return
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        history_text = ""
        for chat in st.session_state.chat_history:
            role = "User" if chat["role"] == "user" else "Mentor"
            history_text += f"{role}: {chat['content']}\n"
        
        mode = st.session_state.chat_mode
        knowledge = KNOWLEDGE_DETAILED if mode == "詳細分析" else KNOWLEDGE_SIMPLE

        prompt = f"""
        あなたは映画分析メンターです。以下の会話履歴と知識ベースをもとに、対話を続けてください。
        モード: {mode}
        
        【知識ベース】
        {knowledge}
        
        【会話履歴】
        {history_text}
        
        【指示】
        - ユーザーの回答を受け止め、肯定・補足してください。
        - 次の視点に移るべきであれば、知識ベースから別の問いを提示してください。
        - 回答の最後に必ず【現時点でのストーリー骨格】というセクションを設け、これまでの会話内容を反映して物語の構造要約を更新・出力してください。
        - 150〜300文字程度で返してください（骨格部分は除く）。
        """
        response = model.generate_content(prompt)
        st.session_state.chat_history.append({"role": "assistant", "content": response.text.strip()})
    except Exception as e: st.error(f"Error: {e}")


# =========================================================
# 5. ヘルパー関数
# =========================================================

def get_current_elapsed_time():
    if st.session_state.status == 'playing':
        return time.time() - st.session_state.start_time + st.session_state.elapsed_offset
    else: return st.session_state.elapsed_offset

def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h:d}:{m:02d}:{s:02d}"
    else: return f"{m:02d}:{s:02d}"

def save_bookmark(label, sentiment=0.0):
    ts = get_current_elapsed_time()
    st.session_state.notes.append({
        "timestamp": ts, "display_time": format_time(ts),
        "category": "クイック反応", "content": label,
        "sentiment": sentiment, "details": []
    })
    st.toast(f"「{label}」を記録しました！", icon="✨")

def calculate_decay_curve(df_notes, duration):
    max_time = int(duration) + 1
    time_index = np.arange(max_time)
    decay_scores = np.zeros(max_time)
    events = {}
    for _, row in df_notes.iterrows():
        if row['category'] == '見返しマーク': continue
        sec = int(row['timestamp'])
        if sec < max_time: events[sec] = row['sentiment']
    LIFETIME = 60.0 
    last_event_time = -999; last_event_score = 0.0
    for t in range(max_time):
        if t in events:
            decay_scores[t] = events[t]; last_event_time = t; last_event_score = events[t]
        elif last_event_time != -999:
            delta_t = t - last_event_time
            if delta_t < LIFETIME:
                ratio = (math.pi / 2) * (delta_t / LIFETIME)
                decay_scores[t] = last_event_score * math.cos(ratio)
            else: decay_scores[t] = 0.0
    return pd.DataFrame({'timestamp': time_index, 'sentiment': decay_scores})

def generate_html_report(df, movie_title, characters=[]):
    char_html = ""
    if characters:
        char_items = ""
        for char in characters:
            char_items += f"""<div style="margin-bottom:12px;padding-bottom:12px;border-bottom:1px dashed #eee;display:flex;align-items:center;"><div style="background:#f0f2f6;width:36px;height:36px;border-radius:50%;display:flex;justify-content:center;align-items:center;margin-right:12px;font-size:1.2rem;">👤</div><div><div style="font-weight:bold;color:#2c3e50;font-size:1.05em;">{html.escape(char['name'])}</div><div style="font-size:0.95em;color:#666;white-space:pre-wrap;margin-top:2px;">{html.escape(char['desc'])}</div></div></div>"""
        char_html = f"""<div style="background:white;padding:25px;margin-bottom:40px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.05);border:1px solid #eee;"><h3 style="color:#FF914D;border-bottom:2px solid #FF914D;padding-bottom:10px;margin-top:0;">👥 登場人物・組織</h3>{char_items}</div>"""
    html_content = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><title>{html.escape(movie_title)} - Log</title><style>body{{font-family:sans-serif;max-width:800px;margin:0 auto;padding:40px 20px;background:#f8f9fa;color:#333}}h1{{border-bottom:4px solid #FF4B4B;padding-bottom:15px;margin-bottom:40px}}.timeline{{position:relative;padding-left:40px}}.timeline::before{{content:'';position:absolute;left:10px;top:0;bottom:0;width:2px;background:#e9ecef}}.note-card{{background:white;border-radius:12px;padding:20px;margin-bottom:25px;border-left:6px solid #FF4B4B;box-shadow:0 4px 15px rgba(0,0,0,0.05)}}.note-card.bookmark{{border-left-color:#FFD700;background:#fffdf0}}.meta{{display:flex;justify-content:space-between;margin-bottom:10px;border-bottom:1px solid #eee;padding-bottom:5px}}.time{{font-weight:bold;color:#FF4B4B}}.category{{background:#eee;padding:2px 10px;border-radius:12px;font-size:0.8em}}.sentiment{{text-align:right;color:#999;font-size:0.9em}}</style></head><body><h1>🎬 {html.escape(movie_title)}</h1>{char_html}<div class="timeline">"""
    for index, row in df.iterrows():
        is_mark = row['category'] in ["見返しマーク", "クイック反応"]
        cls = "note-card bookmark" if is_mark else "note-card"
        s_txt = f"{row['sentiment']:.2f}" if not is_mark else "-"
        safe_content = html.escape(row['content'])
        html_content += f"""<div class="{cls}"><div class="meta"><span class="time">{row['display_time']}</span><span class="category">{row['category']}</span></div><div class="content">{safe_content}</div><div class="sentiment">Score: {s_txt}</div></div>"""
    html_content += "</div></body></html>"
    return html_content

def generate_analysis_process_report(df, movie_title):
    html_content = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><title>{html.escape(movie_title)} Detail</title><style>body{{font-family:sans-serif;max-width:900px;margin:0 auto;padding:20px;background:#f4f6f8}}.card{{background:white;padding:20px;margin-bottom:20px;border-radius:8px}}.chip{{display:inline-block;padding:4px 8px;margin:2px;border-radius:12px;font-size:0.9em;border:1px solid #ddd;background:#fff}}.pos{{border-color:#b2f5ea;color:#006d5b;background:#e6fffa}}.neg{{border-color:#fed7d7;color:#c53030;background:#fff5f5}} .arrow{{color:#999;margin:0 4px}} .orig{{font-size:0.8em;color:#888}}</style></head><body><h1>{html.escape(movie_title)} 分析詳細</h1>"""
    for index, row in df.iterrows():
        if row['category'] in ["見返しマーク", "クイック反応"]: continue
        details = row.get('details', [])
        chips_html = ""
        if details:
            for d in details:
                final = d['score']; orig = d.get('original_score', final)
                cls = "pos" if final > 0 else "neg" if final < 0 else ""
                disp = f"<span class='orig'>{orig:+.1f}</span><span class='arrow'>➡</span><b>{final:+.1f}</b>" if abs(final-orig)>0.001 else f"<b>{final:+.1f}</b>"
                chips_html += f"""<span class="chip {cls}">{d['term']} [{disp}] <span style="font-size:0.8em;color:#666">({d['reason']})</span></span>"""
        else: chips_html = "<span style='color:#999;'>感情語なし (スコア0)</span>"
        html_content += f"""<div class="card"><h3>{row['display_time']} {row['category']}</h3><p>{html.escape(row['content'])}</p><div>{chips_html}</div></div>"""
    html_content += "</body></html>"
    return html_content


# =========================================================
# 5. サイドバー & メイン画面
# =========================================================
with st.sidebar:
    st.header("⚙️ 設定")
    
    # 登場人物
    st.subheader("👥 登場人物・組織")
    with st.form("add_char_form", clear_on_submit=True):
        c_name = st.text_input("名前・組織名", placeholder="例: ジョン・ドゥ")
        c_desc = st.text_area("詳細メモ", placeholder="例: 主人公。元刑事で正義感が強い。", height=100)
        if st.form_submit_button("追加", use_container_width=True) and c_name:
            st.session_state.characters.append({"name": c_name, "desc": c_desc}); st.rerun()
    if st.session_state.characters:
        st.markdown("---")
        st.caption("登録済みリスト (編集可能)")
        for i, char in enumerate(st.session_state.characters):
            with st.expander(f"👤 {char['name']}", expanded=False):
                def update_name(idx=i): st.session_state.characters[idx]['name'] = st.session_state[f"cn_{idx}"]
                def update_desc(idx=i): st.session_state.characters[idx]['desc'] = st.session_state[f"cd_{idx}"]
                st.text_input("名前", value=char['name'], key=f"cn_{i}", on_change=update_name)
                st.text_area("メモ", value=char['desc'], key=f"cd_{i}", on_change=update_desc)
                if st.button("削除", key=f"del_{i}", use_container_width=True):
                    st.session_state.characters.pop(i); st.rerun()
    
    st.divider()
    
    # AI設定
    st.subheader("🤖 AI設定")
    api_key = st.text_input("Gemini API Key", type="password", value=st.session_state.gemini_api_key)
    if api_key: st.session_state.gemini_api_key = api_key; st.caption("✅ 有効")
    else: st.caption("⚠️ 無効")
    
    st.divider()
    uploaded_file = st.file_uploader("CSV比較", type=['csv'])
    if not is_dict_loaded: st.error("⚠️ 辞書なし")
    
    st.divider()
    new_cat = st.text_input("追加カテゴリ", placeholder="例: 音響")
    if st.button("追加", use_container_width=True) and new_cat and new_cat not in st.session_state.custom_categories:
        st.session_state.custom_categories.append(new_cat); st.success("追加しました")
    if st.session_state.custom_categories: st.caption("カスタム項目:"); [st.markdown(f"- {c}") for c in st.session_state.custom_categories]

# メイン画面
st.title("🎬 CineLog")
st.caption("心の動きをデータ化するアプリケーション。")
movie_title = st.text_input("作品名", placeholder="作品名を入力 (例: 市民ケーン)", label_visibility="collapsed")
st.write("")

col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
with col1:
    if st.session_state.status in ['ready', 'paused']:
        if st.button("▶ 視聴開始 / 再開", type="primary", use_container_width=True):
            st.session_state.status = 'playing'
            st.session_state.start_time = time.time()
            st.rerun()
with col2:
    if st.session_state.status == 'playing':
        if st.button("⏸ 一時停止", use_container_width=True):
            st.session_state.status = 'paused'
            st.session_state.elapsed_offset += time.time() - st.session_state.start_time
            st.rerun()
with col3:
    current_ts = get_current_elapsed_time()
    st.metric("Time", format_time(current_ts), label_visibility="collapsed")
with col4:
    if st.session_state.status != 'ready':
        if st.button("■ 視聴終了 / 分析へ", type="secondary", use_container_width=True):
            if st.session_state.status == 'playing':
                st.session_state.elapsed_offset += time.time() - st.session_state.start_time
            st.session_state.status = 'finished'
            st.rerun()


# =========================================================
# 7. 入力エリア
# =========================================================
if st.session_state.status in ['playing', 'paused']:
    st.divider()
    components.html("""<script>const doc=window.parent.document;if(!window.parent._k){const k=e=>{if(e.key==='Escape'){if(doc.activeElement)doc.activeElement.blur();return}if(e.target.tagName==='TEXTAREA'||e.target.tagName==='INPUT')return;if(e.key==='1'){const b=Array.from(doc.querySelectorAll('button')).find(e=>e.innerText.includes('見返し'));if(b)b.click()}else if(e.key==='2'){const b=Array.from(doc.querySelectorAll('button')).find(e=>e.innerText.includes('感動'));if(b)b.click()}else if(e.key==='3'){const b=Array.from(doc.querySelectorAll('button')).find(e=>e.innerText.includes('しんみり'));if(b)b.click()}};doc.addEventListener('keydown',k);window.parent._k=true}</script>""", height=0, width=0)

    st.subheader(f"📝 リアクション & メモ")
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("🚩 見返しマーク (Key:1)", use_container_width=True): save_bookmark("見返しマーク", 0.0)
    with b2:
        if st.button("😂 感動した！ (Key:2)", use_container_width=True): save_bookmark("感動した！", 1.0)
    with b3:
        if st.button("😢 しんみり... (Key:3)", use_container_width=True): save_bookmark("しんみり...", 0.5)
    st.caption("キーボード: [1][2][3] / [Esc]で入力解除")
    st.write("")

    def save_note():
        ts = get_current_elapsed_time()
        category = st.session_state.get("input_category", "感想")
        content = st.session_state.get("input_content", "")
        if content.strip():
            sentiment, details = analyze_sentiment_advanced(content)
            st.session_state.notes.append({"timestamp": ts, "display_time": format_time(ts), "category": category, "content": content, "sentiment": sentiment, "details": details})
            st.toast("メモを記録しました", icon="✅")

    with st.form("analysis_form", clear_on_submit=True):
        base_cats = ["感想", "ストーリー", "ショットの構図", "音楽", "色彩"]
        all_cats = base_cats + st.session_state.custom_categories
        c1, c2 = st.columns([1, 3])
        with c1: st.selectbox("カテゴリ", options=all_cats, key="input_category")
        with c2: st.text_area("内容", key="input_content", height=200, placeholder="分析内容を入力...")
        st.write("")
        submit = st.form_submit_button("メモを記録する", on_click=save_note, use_container_width=True, type="primary")


# =========================================================
# 8. 分析結果画面
# =========================================================
if st.session_state.status == 'finished':
    st.divider()
    st.header("📊 分析レポート")
    
    if st.session_state.characters:
        with st.expander("👥 登場人物・組織メモを確認する", expanded=True):
            for char in st.session_state.characters:
                st.markdown(f"**{char['name']}**: {char['desc']}")
                st.divider()

    if not st.session_state.notes:
        st.warning("記録されたメモがありません。")
    else:
        df = pd.DataFrame(st.session_state.notes)
        
        st.subheader("1. 感情曲線")
        df_chart = df.sort_values('timestamp').copy()
        max_time = max(st.session_state.elapsed_offset, df['timestamp'].max())
        if max_time == 0: max_time = 60
        df_decay = calculate_decay_curve(df_chart, max_time)
        df_current = df_decay.set_index('timestamp')
        label = f"今回 - {movie_title if movie_title else '無題'}"
        df_current.columns = [label]

        if uploaded_file:
            try:
                df_past = pd.read_csv(uploaded_file)
                df_p_s = df_past[['timestamp', 'sentiment']].copy().fillna(0)
                df_p_s['timestamp'] = df_p_s['timestamp'].astype(int)
                df_p_s = df_p_s.set_index('timestamp').groupby('timestamp').mean()
                p_label = f"過去 - {uploaded_file.name}"
                df_p_s.columns = [p_label]
                merged = df_current.join(df_p_s, how='outer').interpolate(method='index').fillna(0)
                st.line_chart(merged)
            except: st.line_chart(df_current, color="#FF4B4B")
        else: st.line_chart(df_current, color="#FF4B4B")

        st.write("")
        st.subheader("2. 鑑賞ログ")
        df = df.sort_values('timestamp')
        timeline_html = '<div class="timeline-container">'
        for index, row in df.iterrows():
            score = row['sentiment']
            is_mark = row['category'] in ["見返しマーク", "クイック反応"]
            if is_mark and row['category'] == "見返しマーク": m_cls, c_cls, s_cls = "marker-mark", "border-mark", ""
            elif score >= 0.1: m_cls, c_cls, s_cls = "marker-pos", "border-pos", "score-pos"
            elif score <= -0.1: m_cls, c_cls, s_cls = "marker-neg", "border-neg", "score-neg"
            else: m_cls, c_cls, s_cls = "", "", ""
            score_txt = "Check Point" if row['category'] == "見返しマーク" else f"Reaction ({score:+.1f})" if row['category'] == "クイック反応" else f"Score: {score:+.2f}"
            safe_content = html.escape(row['content'])
            timeline_html += f"""<div class="timeline-item"><div class="timeline-time">{row['display_time']}</div><div class="timeline-marker {m_cls}"></div><div class="timeline-content {c_cls}"><div style="display:flex;justify-content:space-between;margin-bottom:8px;"><span style="background:#F3F4F6;padding:2px 10px;border-radius:10px;font-size:0.8rem;font-weight:bold;color:#6B7280;">{row['category']}</span><span style="font-size:0.8rem;">{score_txt}</span></div><div style="font-size:1rem;line-height:1.5;">{safe_content}</div></div></div>"""
        timeline_html += '</div>'
        st.markdown(timeline_html, unsafe_allow_html=True)
    
    st.divider()
    st.subheader("💾 データの保存")
    col_dl1, col_dl2, col_dl3 = st.columns(3)
    safe_title = movie_title if movie_title else "analysis"
    csv = df_decay.to_csv(index=False).encode('utf-8-sig')
    col_dl1.download_button("📈 感情データ (CSV)", csv, f'{safe_title}_sentiment_curve.csv', 'text/csv')
    char_list = st.session_state.characters
    html_log = generate_html_report(df, safe_title, char_list).encode('utf-8')
    col_dl2.download_button("📄 鑑賞ログ (HTML)", html_log, f'{safe_title}_log.html', 'text/html')
    html_detail = generate_analysis_process_report(df, safe_title).encode('utf-8')
    col_dl3.download_button("🔍 分析詳細 (HTML)", html_detail, f'{safe_title}_details.html', 'text/html')
    
    if st.session_state.gemini_api_key:
        st.divider()
        st.subheader("🤖 AI感想戦（深堀りチャット）")
        if not st.session_state.get('chat_initialized', False): init_chat_with_analysis(df)
        for chat in st.session_state.chat_history:
            with st.chat_message(chat["role"]): st.write(chat["content"])
        if prompt := st.chat_input("AIに返信して分析を深める..."):
            process_chat_input(prompt)
            st.rerun()

    st.write("")
    if st.button("新しい分析を始める", use_container_width=True):
        for key in ['status', 'start_time', 'elapsed_offset', 'notes', 'chat_history', 'chat_initialized', 'characters']:
             if key in st.session_state: del st.session_state[key]
        st.rerun()