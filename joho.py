import streamlit as st
from datetime import datetime, timedelta
import html 

# --- アプリの基本設定 ---
st.set_page_config(page_title="映画鑑賞メモツール")

# --- 状態管理 ---
def initialize_state(clear_memos=False):
    """セッションステートを初期化またはリセットします。"""
    if 'start_time' not in st.session_state or clear_memos:
        st.session_state.start_time = None
    if 'movie_title' not in st.session_state or clear_memos:
        st.session_state.movie_title = ""
    if 'memos' not in st.session_state or clear_memos:
        st.session_state.memos = []
    if 'memo_id_counter' not in st.session_state or clear_memos:
        st.session_state.memo_id_counter = 0
    
    if 'is_shot_timing' not in st.session_state or clear_memos:
        st.session_state.is_shot_timing = False
    if 'shot_start_time' not in st.session_state or clear_memos:
        st.session_state.shot_start_time = None
        
    # --- ★ st.form の外でテキストエリアを管理するためのキー ---
    if 'current_memo_text_area' not in st.session_state or clear_memos:
        st.session_state.current_memo_text_area = ""
    # ---------------------------------------------------

# --- セッションステートの初期化（初回実行時のみ） ---
initialize_state(clear_memos=False)

# --- ヘルパー関数: 経過時間をフォーマット ---
def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# --- 経過時間計算 ---
def get_elapsed_time():
    """現在の経過時間を計算します。"""
    if not st.session_state.start_time:
        return timedelta(0)
    return datetime.now() - st.session_state.start_time

# --- HTML生成関数 ---
def generate_html():
    """メモのリストからHTML文字列を生成します。"""
    title = st.session_state.movie_title or "無題の映画"
    
    # HTMLのヘッダーとスタイル
    html_content = f"""
    <html>
    <head>
        <title>{html.escape(title)} のメモ</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: sans-serif; margin: 2em; line-height: 1.6; }}
            h1 {{ color: #333; }}
            .memo {{ border: 1px solid #ddd; border-radius: 8px; margin-bottom: 1em; padding: 1em; }}
            .time {{ font-weight: bold; color: #007bff; font-size: 1.2em; }}
            .text {{ white-space: pre-wrap; word-wrap: break-word; }}
        </style>
    </head>
    <body>
    <h1>{html.escape(title)} のメモ</h1>
    """
    
    # メモを追加（時系列順）
    for memo in st.session_state.memos:
        html_content += f"""
        <div class="memo">
            <div class="time">🎬 {memo['time']}</div>
            <div class="text">{html.escape(memo['text'])}</div>
        </div>
        """
    
    html_content += "</body></html>"
    return html_content

# --- コールバック関数: メモ削除 ---
def delete_memo(index):
    if 0 <= index < len(st.session_state.memos):
        st.session_state.memos.pop(index)

# --- ★ショットタイマー用のコールバック関数を修正 ---
def start_shot_timer():
    """ショットタイマーを開始します。"""
    st.session_state.is_shot_timing = True
    st.session_state.shot_start_time = datetime.now()

def stop_shot_timer_and_update_memo():
    """タイマーを停止し、計測結果をメモ欄に追記します。"""
    if st.session_state.shot_start_time:
        shot_duration = datetime.now() - st.session_state.shot_start_time
        duration_str = f"（計測したショット長: {shot_duration.total_seconds():.1f} 秒）"
        
        # ★ st.form をやめたため、st.session_state.current_memo_text_area が常に最新の値を保持している
        current_text = st.session_state.get("current_memo_text_area", "")
        
        if current_text:
            st.session_state.current_memo_text_area = f"{current_text}\n{duration_str}"
        else:
            st.session_state.current_memo_text_area = duration_str
            
    st.session_state.is_shot_timing = False
    st.session_state.shot_start_time = None
# ---------------------------------------------

# --- コールバック関数: リセット ---
def reset_all():
    """状態をすべてリセットします。"""
    initialize_state(clear_memos=True)
    # テキストエリアも明示的にリセット
    st.session_state.current_memo_text_area = ""

# --- ★「メモを記録」ボタン用のコールバック関数 ---
def add_memo():
    """現在のテキストエリアの内容をメモに追加し、テキストエリアをクリアします。"""
    current_memo_text = st.session_state.current_memo_text_area
    if current_memo_text:
        timestamp_str = format_timedelta(get_elapsed_time())
        
        new_id = st.session_state.memo_id_counter
        st.session_state.memo_id_counter += 1
        
        st.session_state.memos.append({
            "id": new_id,
            "time": timestamp_str,
            "text": current_memo_text,
        })
        
        # テキストエリアをクリア
        st.session_state.current_memo_text_area = ""
    else:
        st.warning("メモ内容を入力してください。")
# ------------------------------------------

# --- メインエリア (ヘッダー) ---
st.title("🎬 映画鑑賞メモツール")

# --- サイドバー (設定エリア) ---
with st.sidebar:
    st.header("設定")
    
    st.session_state.movie_title = st.text_input(
        "映画のタイトル", 
        st.session_state.movie_title,
        placeholder="例: ショーシャンクの空に"
    )

    col1, col2 = st.columns(2)

    if st.session_state.start_time is None:
        if col1.button("▶️ 視聴開始", use_container_width=True, type="primary"):
            initialize_state(clear_memos=False) 
            st.session_state.start_time = datetime.now()
            st.rerun()
    else:
        col1.write("（視聴中）") 

    if col2.button("🔄 リセット", use_container_width=True, on_click=reset_all):
        st.rerun()


    if not st.session_state.start_time:
        st.info("映画のタイトルを入力し、「視聴開始」ボタンを押してください。")
    else:
        elapsed_time = get_elapsed_time()
        st.info(f"経過時間: {format_timedelta(elapsed_time)}")

    if st.session_state.memos:
        st.divider()
        st.download_button(
            label="📁 メモをHTMLで保存",
            data=generate_html(),
            file_name=f"{st.session_state.movie_title or 'memo'}.html",
            mime="text/html",
            use_container_width=True,
            help="現在のすべてのメモをHTMLファイルとしてダウンロードします。"
        )

# --- メインエリア (入力 & メモ表示エリア) ---
st.header(f"🗒️ 「{st.session_state.movie_title or '（タイトル未設定）'}」のメモ")

if st.session_state.start_time:
    
    st.subheader("⏱️ ショットタイマー")
    if not st.session_state.is_shot_timing:
        st.button(
            "🎬 ショット計測開始", 
            on_click=start_shot_timer,
            use_container_width=True
        )
    else:
        shot_duration = datetime.now() - st.session_state.shot_start_time
        st.button(
            f"⏹️ 計測停止 (現在 {shot_duration.total_seconds():.1f} 秒)", 
            on_click=stop_shot_timer_and_update_memo,
            use_container_width=True,
            type="primary",
            help="このボタンを押すと計測を停止し、結果を下の『メモを追加』欄に追記します。"
        )

    st.divider() 

    # --- ★ st.form を削除 ---
    st.subheader("✍️ メモを追加")
    
    # 'key' を使い、st.session_state と双方向にバインドする
    st.text_area(
        "気になったこと、伏線など", 
        key="current_memo_text_area",
        placeholder="このシーンの照明が印象的..."
    )

    # ★ st.form_submit_button を st.button に変更し、コールバックを接続
    st.button(
        "📝 メモを記録",
        on_click=add_memo,
        type="primary",
        use_container_width=True
    )
    # -----------------------

    st.divider()

else:
    st.info("サイドバーから視聴を開始すると、ここにメモが記録されます。")


# --- メモ一覧の表示 ---
if not st.session_state.memos and st.session_state.start_time:
    st.info("まだメモはありません。フォームから最初のメモを記録しましょう。")

for i, memo in enumerate(reversed(st.session_state.memos)):
    original_index = len(st.session_state.memos) - 1 - i
    
    with st.container(border=True):
        col1, col2 = st.columns([1, 4])
        
        with col1:
            st.metric(label="記録時間", value=memo["time"])
            
            st.button(
                "🗑️ 削除", 
                key=f"delete_{memo['id']}",
                on_click=delete_memo, 
                args=(original_index,)
            )

        with col2:
            if memo["text"]:
                st.write(memo["text"])