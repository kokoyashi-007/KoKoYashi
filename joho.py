import streamlit as st
import pandas as pd
import numpy as np
import time
# 自然言語処理ライブラリ Janome (形態素解析器)
from janome.tokenizer import Tokenizer
import os
import re
# JavaScript埋め込み用
import streamlit.components.v1 as components
# 数学関数（コサイン減衰などで使用）
import math
# HTMLエスケープ用（セキュリティ対策）
import html

# =========================================================
# 0. アプリケーション設定 & CSS (UIデザイン)
# =========================================================
# ページ設定: タイトルとレイアウト（wideモードで横幅を有効活用）
st.set_page_config(page_title="CineLog - 映画分析", layout="wide")

# CSSによるスタイリング
# Streamlitの標準スタイルを上書きし、洗練されたデザインにします。
st.markdown("""
<style>
    /* ベースフォント設定: 視認性の高いゴシック体を優先指定 */
    body {
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
        background-color: #FAFAFA; color: #333;
    }
    /* アプリタイトル: グラデーションでモダンな印象に */
    h1 {
        background: linear-gradient(45deg, #FF4B4B, #FF914D);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-weight: 800; letter-spacing: -1px; margin-bottom: 0.5rem;
    }
    /* タイマー表示: 等幅フォントでデジタル時計風に */
    [data-testid="stMetricValue"] {
        font-family: 'Courier New', Courier, monospace;
        font-weight: bold; font-size: 3rem !important;
        color: #444; text-shadow: 2px 2px 0px rgba(0,0,0,0.1);
    }
    /* ボタン: ホバー時の浮き上がりアニメーション */
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
    /* テキストエリア: 白背景固定・フォーカス時のアクセントカラー */
    .stTextArea textarea {
        border-radius: 12px; border: 1px solid #E0E0E0;
        background-color: #FFF !important; color: #333 !important;
        font-size: 16px; line-height: 1.6; padding: 16px;
        transition: all 0.3s ease; box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
    }
    .stTextArea textarea:focus {
        border-color: #FF4B4B; box-shadow: 0 0 0 3px rgba(255, 75, 75, 0.15);
    }
    /* タイムライン（鑑賞ログ）用スタイル */
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
    
    /* フェードインアニメーション */
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .block-container { animation: fadeIn 0.6s ease-out forwards; }
</style>
""", unsafe_allow_html=True)


# =========================================================
# 1. ステート管理 (State Management)
# =========================================================
# 解説:
# Streamlitは操作のたびにスクリプト全体を再実行するため、
# `st.session_state` を使って変数の値を保持します。
# これにより、ストップウォッチの状態や入力したメモが消えずに維持されます。

if 'status' not in st.session_state:
    st.session_state.status = 'ready' # アプリの状態 (ready, playing, paused, finished)

if 'start_time' not in st.session_state:
    st.session_state.start_time = None # 再生開始時刻

if 'elapsed_offset' not in st.session_state:
    st.session_state.elapsed_offset = 0.0 # 一時停止中の経過時間を蓄積

if 'notes' not in st.session_state:
    st.session_state.notes = [] # 入力された全メモデータ

if 'custom_categories' not in st.session_state:
    st.session_state.custom_categories = [] # ユーザーが追加したカテゴリ

if 'sentiment_dict' not in st.session_state:
    st.session_state.sentiment_dict = None # 読み込んだ辞書データをキャッシュ


# =========================================================
# 2. 自然言語処理 (NLP) ルール定義
# =========================================================

# 否定語リスト: これらが感情語の後に続くと、スコアを反転させます。
NEGATION_WORDS = ['ない', 'ず', 'ぬ', 'まい']

# 逆接語リスト: これらが出現すると、それ以降の文章の重要度（重み）を上げます。
ADVERSATIVE_WORDS = ['しかし', 'でも', 'だが', 'ところが', 'けど', 'けれど', 'けれども']

# 連語（コンパウンド）ルール: 単語の組み合わせでスコアを決めるリスト。
COMPOUND_RULES = {
    ('値段', '高い'): -1.0, ('敷居', '高い'): -1.0, ('プライド', '高い'): -0.8,
    ('腰', '重い'): -0.8, ('口', '軽い'): -0.8, ('目', 'ない'): 1.0,
    ('音沙汰', 'ない'): -1.0, ('飽き', 'こない'): 1.0, ('テンション', '高い'): 1.0,
    ('器', '大きい'): 1.0, ('コストパフォーマンス', '高い'): 1.0,
    ('コスパ', '高い'): 1.0, ('気', '強い'): -0.5,
    # ポジティブな「感じ」の表現
    ('いい', '感じ'): 1.0, ('良い', '感じ'): 1.0, ('よい', '感じ'): 1.0,
}

# ---------------------------------------------------------
# 辞書読み込み関数 (キャッシュ対応)
# ---------------------------------------------------------
# @st.cache_resource: 重い処理（ファイル読み込みなど）の結果を保存し、
# 2回目以降の実行をスキップして高速化するデコレータ。
@st.cache_resource
def load_sentiment_dictionary():
    """外部の感情極性辞書(pn_ja.dic)を読み込む"""
    candidates = [os.path.join('dic', 'pn_ja.dic'), 'pn_ja.dic']
    dic_lemma = {}
    loaded = False

    for path in candidates:
        if os.path.exists(path):
            try:
                # 【修正点】header=None を追加
                # 辞書ファイルにはヘッダー行がないことが多いため、
                # 1行目からデータとして読み込むように指定します。
                df_pn = pd.read_csv(path, encoding="sjis", sep=":", names=["lemma", "reading", "pos", "score"], header=None)
                
                # 辞書型に変換 {単語: スコア}
                dic_lemma = df_pn.set_index('lemma')['score'].to_dict()
                loaded = True
                break
            except Exception: pass
    return dic_lemma, loaded

@st.cache_resource
def get_tokenizer():
    return Tokenizer()

# アプリ起動時にロード
sentiment_dict, is_dict_loaded = load_sentiment_dictionary()


# =========================================================
# 3. 感情分析エンジン
# =========================================================
def analyze_sentiment_advanced(text):
    """
    高度な感情分析ロジック
    
    プロセス解説:
    1. 正規化: 表記ゆれを統一します（例: ありません -> ないです）。
    2. 形態素解析: Janomeを使って文章を単語に分割します。
    3. 文脈解析:
       - 逆接ブースト: 「しかし」以降の単語の重みを1.5倍にします。
       - 連語判定: 「値段+高い」などの組み合わせを優先評価します。
       - 辞書マッチ: 単語辞書からスコアを取得。ネガティブ語は0.6倍して緩和します。
       - 否定反転: 「ない」などが続けばスコアを反転します。
    4. 加重平均: 各単語のスコアと重みを計算し、全体の平均値を出します。
    """
    if not text: return 0.0, []

    # 1. 前処理
    text = text.replace("ありません", "ないです")
    
    t = get_tokenizer()
    tokens = list(t.tokenize(text))
    
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
        
        # 2. 逆接チェック
        is_adversative = False
        if pos == '接続詞' and base_form in ADVERSATIVE_WORDS: is_adversative = True
        elif pos == '助詞' and sub_pos == '接続助詞' and base_form in ['が', 'けど', 'けれど', 'けれども']: is_adversative = True
        if is_adversative: current_boost = 1.5
        
        current_score = 0.0
        original_score = 0.0 # 辞書や連語の元のスコアを記録用
        found_sentiment = False
        matched_term = base_form
        reason = ""
        
        # 3. 連語チェック (優先度高)
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
        
        # 4. 辞書チェック
        if not found_sentiment:
            if pos in target_pos and base_form in sentiment_dict:
                raw_score = sentiment_dict[base_form]
                original_score = raw_score # ログ用に生の辞書値を保存
                
                # 分析感度向上のため、ノイズ除去とネガティブ緩和を撤廃
                # 辞書のスコアをそのまま採用し、微細な感情も拾うように変更
                current_score = raw_score
                
                found_sentiment = True
                reason = "辞書マッチ"
        
        # 5. 否定語チェック
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
            
            # 【修正】詳細ログに「元のスコア」も含める
            calc_log.append({
                'term': matched_term,
                'score': current_score,
                'original_score': original_score,
                'reason': log_reason,
                'boost_factor': current_boost
            })
        i += 1

    # 6. 集計
    count = len(matched_scores)
    if count == 0: return 0.0, []
    if count == 1: return matched_scores[0], calc_log
        
    weighted_sum = 0.0
    total_weight = 0.0
    for idx, item in enumerate(calc_log):
        score = matched_scores[idx]
        base_weight = 1.0
        final_weight = base_weight * item['boost_factor']
        weighted_sum += score * final_weight
        total_weight += final_weight
        item['weight'] = final_weight
        
    final_score = weighted_sum / total_weight
    return max(-1.0, min(1.0, final_score)), calc_log


# =========================================================
# 4. ヘルパー関数
# =========================================================

def get_current_elapsed_time():
    if st.session_state.status == 'playing':
        return time.time() - st.session_state.start_time + st.session_state.elapsed_offset
    else:
        return st.session_state.elapsed_offset

def format_time(seconds):
    """秒数を MM:SS 形式に変換（長時間対応）"""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    else:
        return f"{m:02d}:{s:02d}"

def save_bookmark(label, sentiment=0.0):
    """リアクションボタン用保存処理"""
    ts = get_current_elapsed_time()
    st.session_state.notes.append({
        "timestamp": ts, "display_time": format_time(ts),
        "category": "クイック反応", "content": label,
        "sentiment": sentiment, "details": []
    })
    st.toast(f"「{label}」を記録しました！", icon="✨")

# --- 感情曲線の「余韻減衰 (Decay)」ロジック ---
def calculate_decay_curve(df_notes, duration):
    """
    感情の「余韻」をシミュレートする関数。
    ある瞬間に発生した感情スコアは、時間が経つにつれて0に戻ると仮定します。
    「コサイン減衰」を使用し、最初はゆっくり、後半で急速に0に戻る自然な曲線を生成します。
    """
    max_time = int(duration) + 1
    time_index = np.arange(max_time)
    decay_scores = np.zeros(max_time)
    
    events = {}
    for _, row in df_notes.iterrows():
        if row['category'] == '見返しマーク': continue
        sec = int(row['timestamp'])
        if sec < max_time:
            events[sec] = row['sentiment']
    
    # 【修正】減衰時間を60秒に短縮（より0に戻りやすくする）
    LIFETIME = 60.0 
    last_event_time = -999
    last_event_score = 0.0
    
    for t in range(max_time):
        if t in events:
            decay_scores[t] = events[t]
            last_event_time = t
            last_event_score = events[t]
        elif last_event_time != -999:
            delta_t = t - last_event_time
            if delta_t < LIFETIME:
                # コサイン減衰式: y = Score * cos( (π/2) * (t / LIFETIME) )
                ratio = (math.pi / 2) * (delta_t / LIFETIME)
                decay_scores[t] = last_event_score * math.cos(ratio)
            else:
                decay_scores[t] = 0.0
    return pd.DataFrame({'timestamp': time_index, 'sentiment': decay_scores})

# HTML生成関数（エスケープ処理追加）
def generate_html_report(df, movie_title):
    html_content = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><title>{html.escape(movie_title)} - Log</title><style>body{{font-family:sans-serif;max-width:800px;margin:0 auto;padding:40px 20px;background:#f8f9fa;color:#333}}h1{{border-bottom:4px solid #FF4B4B;padding-bottom:15px;margin-bottom:40px}}.timeline{{position:relative;padding-left:40px}}.timeline::before{{content:'';position:absolute;left:10px;top:0;bottom:0;width:2px;background:#e9ecef}}.note-card{{background:white;border-radius:12px;padding:20px;margin-bottom:25px;border-left:6px solid #FF4B4B;box-shadow:0 4px 15px rgba(0,0,0,0.05)}}.note-card.bookmark{{border-left-color:#FFD700;background:#fffdf0}}.meta{{display:flex;justify-content:space-between;margin-bottom:10px;border-bottom:1px solid #eee;padding-bottom:5px}}.time{{font-weight:bold;color:#FF4B4B}}.category{{background:#eee;padding:2px 10px;border-radius:12px;font-size:0.8em}}.sentiment{{text-align:right;color:#999;font-size:0.9em}}</style></head><body><h1>🎬 {html.escape(movie_title)}</h1><div class="timeline">"""
    for index, row in df.iterrows():
        is_mark = row['category'] in ["見返しマーク", "クイック反応"]
        cls = "note-card bookmark" if is_mark else "note-card"
        s_txt = f"{row['sentiment']:.2f}" if not is_mark else "-"
        # 【修正】コンテンツのHTMLエスケープ（XSS対策）
        safe_content = html.escape(row['content'])
        html_content += f"""<div class="{cls}"><div class="meta"><span class="time">{row['display_time']}</span><span class="category">{row['category']}</span></div><div class="content">{safe_content}</div><div class="sentiment">Score: {s_txt}</div></div>"""
    html_content += "</div></body></html>"
    return html_content

def generate_analysis_process_report(df, movie_title):
    # 【修正】分析プロセスの可視化強化（辞書値と最終値を併記）
    html_content = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><title>{html.escape(movie_title)} Detail</title><style>body{{font-family:sans-serif;max-width:900px;margin:0 auto;padding:20px;background:#f4f6f8}}.card{{background:white;padding:20px;margin-bottom:20px;border-radius:8px}}.chip{{display:inline-block;padding:4px 8px;margin:2px;border-radius:12px;font-size:0.9em;border:1px solid #ddd;background:#fff}}.pos{{border-color:#b2f5ea;color:#006d5b;background:#e6fffa}}.neg{{border-color:#fed7d7;color:#c53030;background:#fff5f5}} .arrow{{color:#999;margin:0 4px}} .orig{{font-size:0.8em;color:#888}}</style></head><body><h1>{html.escape(movie_title)} 分析詳細</h1>"""
    for index, row in df.iterrows():
        if row['category'] in ["見返しマーク", "クイック反応"]: continue
        details = row.get('details', [])
        sentiment = row['sentiment']
        chips_html = ""
        if details:
            for d in details:
                final_score = d['score']
                orig_score = d.get('original_score', final_score) # 未設定なら同じ
                cls = "pos" if final_score > 0 else "neg" if final_score < 0 else ""
                
                # スコアの変化を可視化 (例: -1.0 → +1.0)
                if final_score != orig_score:
                    score_disp = f"<span class='orig'>{orig_score:+.1f}</span><span class='arrow'>➡</span><b>{final_score:+.1f}</b>"
                else:
                    score_disp = f"<b>{final_score:+.1f}</b>"

                chips_html += f"""<span class="chip {cls}">{d['term']} [{score_disp}] <span style="font-size:0.8em;color:#666">({d['reason']})</span></span>"""
        else:
            chips_html = "<span style='color:#999;'>感情語なし (スコア0)</span>"
            
        html_content += f"""<div class="card"><h3>{row['display_time']} {row['category']}</h3><p>{html.escape(row['content'])}</p><div>{chips_html}</div></div>"""
    html_content += "</body></html>"
    return html_content


# =========================================================
# 5. サイドバー & メイン画面
# =========================================================
with st.sidebar:
    st.header("⚙️ 設定")
    st.subheader("📊 比較用データ")
    uploaded_file = st.file_uploader("CSVをアップロード", type=['csv'])
    
    if not is_dict_loaded:
        st.error("⚠️ 辞書ファイル(pn_ja.dic)が見つかりません")
    
    st.divider()
    st.subheader("➕ 分析項目の追加")
    new_cat = st.text_input("項目名", placeholder="例: 音響効果")
    if st.button("項目を追加", use_container_width=True):
        if new_cat and new_cat not in st.session_state.custom_categories:
            st.session_state.custom_categories.append(new_cat)
            st.success(f"「{new_cat}」を追加しました")
    if st.session_state.custom_categories:
        st.caption("現在のカスタム項目:")
        for c in st.session_state.custom_categories: st.markdown(f"- {c}")

st.title("🎬 CineLog")
st.caption("映画を「分析的」に鑑賞し、心の動きをデータ化するアプリケーション")
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
            st.session_state.status = 'finished'
            if st.session_state.status == 'playing':
                st.session_state.elapsed_offset += time.time() - st.session_state.start_time
            st.rerun()


# =========================================================
# 7. 入力エリア & JSキーボード操作
# =========================================================
if st.session_state.status in ['playing', 'paused']:
    st.divider()
    
    # JS埋め込み: キーボード操作 & 重複登録防止
    components.html(
        """
        <script>
        const doc = window.parent.document;
        
        const keyHandler = function(e) {
            // Escキー: フォーカス解除
            if (e.key === 'Escape') {
                if (doc.activeElement) doc.activeElement.blur();
                return;
            }
            // 入力中は無効化
            if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;

            if (e.key === '1') {
                const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('見返しマーク'));
                if (btn) btn.click();
            } else if (e.key === '2') {
                const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('感動した'));
                if (btn) btn.click();
            } else if (e.key === '3') {
                const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('しんみり'));
                if (btn) btn.click();
            }
        };

        // 既存リスナー削除（リラン時の多重登録防止）
        if (window.parent.cinelogKeyHandler) {
            doc.removeEventListener('keydown', window.parent.cinelogKeyHandler);
        }
        window.parent.cinelogKeyHandler = keyHandler;
        doc.addEventListener('keydown', keyHandler);
        </script>
        """, height=0, width=0
    )

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
            st.session_state.notes.append({
                "timestamp": ts, "display_time": format_time(ts),
                "category": category, "content": content,
                "sentiment": sentiment, "details": details
            })
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
    
    if not st.session_state.notes:
        st.warning("記録されたメモがありません。")
    else:
        df = pd.DataFrame(st.session_state.notes)
        
        # 1. 感情曲線
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
            except:
                st.line_chart(df_current, color="#FF4B4B")
        else:
            st.line_chart(df_current, color="#FF4B4B")

        # 2. ログ
        st.write("")
        st.subheader("2. 鑑賞ログ")
        df = df.sort_values('timestamp')
        timeline_html = '<div class="timeline-container">'
        for index, row in df.iterrows():
            score = row['sentiment']
            is_mark = row['category'] in ["見返しマーク", "クイック反応"]
            if is_mark and row['category'] == "見返しマーク":
                m_cls, c_cls, s_cls = "marker-mark", "border-mark", ""
            elif score >= 0.1:
                m_cls, c_cls, s_cls = "marker-pos", "border-pos", "score-pos"
            elif score <= -0.1:
                m_cls, c_cls, s_cls = "marker-neg", "border-neg", "score-neg"
            else:
                m_cls, c_cls, s_cls = "", "", ""
            
            score_txt = "Check Point" if row['category'] == "見返しマーク" else f"Reaction ({score:+.1f})" if row['category'] == "クイック反応" else f"Score: {score:+.2f}"
            # 安全なHTML生成（エスケープ処理）
            safe_content = html.escape(row['content'])
            timeline_html += f"""
<div class="timeline-item">
<div class="timeline-time">{row['display_time']}</div>
<div class="timeline-marker {m_cls}"></div>
<div class="timeline-content {c_cls}">
<div style="display:flex; justify-content:space-between; margin-bottom:8px;">
<span style="background:#F3F4F6; padding:2px 10px; border-radius:10px; font-size:0.8rem; font-weight:bold; color:#6B7280;">{row['category']}</span>
<span style="font-size:0.8rem;">{score_txt}</span>
</div>
<div style="font-size:1rem; line-height:1.5;">{safe_content}</div>
</div>
</div>"""
        timeline_html += '</div>'
        st.markdown(timeline_html, unsafe_allow_html=True)

    # 保存
    st.divider()
    st.subheader("💾 データの保存")
    col_dl1, col_dl2, col_dl3 = st.columns(3)
    safe_title = movie_title if movie_title else "analysis"
    
    csv = df_decay.to_csv(index=False).encode('utf-8-sig')
    col_dl1.download_button("📈 感情データ (CSV)", csv, f'{safe_title}_sentiment_curve.csv', 'text/csv')
    
    html_log = generate_html_report(df, safe_title).encode('utf-8')
    col_dl2.download_button("📄 鑑賞ログ (HTML)", html_log, f'{safe_title}_log.html', 'text/html')
    
    html_detail = generate_analysis_process_report(df, safe_title).encode('utf-8')
    col_dl3.download_button("🔍 分析詳細 (HTML)", html_detail, f'{safe_title}_details.html', 'text/html')

    st.write("")
    if st.button("新しい分析を始める", use_container_width=True):
        for key in ['status', 'start_time', 'elapsed_offset', 'notes']:
             if key in st.session_state: del st.session_state[key]
        st.rerun()