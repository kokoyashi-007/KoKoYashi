import streamlit as st
from datetime import datetime, timedelta
import html 

# --- アプリの基本設定 ---
st.set_page_config(page_title="映画鑑賞メモツール")

# --- ★メモ項目 (変更点) ---
# メモの項目を辞書として定義。キーはセッションステートのキー、値は表示ラベル
MEMO_FIELDS = {
    "memo_input_story": "ストーリー",
    "memo_input_composition": "ショットの構図",
    "memo_input_music": "音楽",
    "memo_input_cut": "カットの種類",
    "memo_input_color": "色彩",
}

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
        
    # --- ★(変更点) 複数のメモ入力欄を初期化 ---
    for key in MEMO_FIELDS.keys():
        if key not in st.session_state or clear_memos:
            st.session_state[key] = ""
    # ----------------------------------------

    if 'is_paused' not in st.session_state or clear_memos:
        st.session_state.is_paused = False
    if 'paused_duration' not in st.session_state or clear_memos:
        st.session_state.paused_duration = timedelta(0)
    if 'pause_start_time' not in st.session_state or clear_memos:
        st.session_state.pause_start_time = None

# --- セッションステートの初期化（初回実行時のみ） ---
initialize_state(clear_memos=False)

# --- ヘルパー関数: 経過時間をフォーマット ---
def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# --- 経過時間計算 (一時停止を考慮) ---
def get_elapsed_time():
    """現在の経過時間を計算します。（一時停止時間を考慮）"""
    if not st.session_state.start_time:
        return timedelta(0)
    
    if st.session_state.is_paused:
        # 一時停止中の場合、最後に記録されたpause_start_timeまでの経過時間を返す
        return st.session_state.pause_start_time - st.session_state.start_time - st.session_state.paused_duration
    else:
        # 実行中の場合、現在時刻までの経過時間を返す
        return datetime.now() - st.session_state.start_time - st.session_state.paused_duration

# --- ★HTML生成関数 (変更点) ---
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
            .text {{ white-space: pre-wrap; word-wrap: break-word; margin-top: 0.5em;}}
            .text b {{ color: #555; }}
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
            <div class="text">
        """
        
        # --- ★(変更点) 5項目の内容をHTMLに追加 ---
        memo_parts = []
        # MEMO_FIELDS のキー（'memo_input_story'）から 'memo_input_' を除いた 'story' を
        # メモ辞書（memo）のキーとして使用します。
        field_keys_map = {key: label for key, label in MEMO_FIELDS.items()}
        
        if memo["story"]:
            memo_parts.append(f"<b>{MEMO_FIELDS['memo_input_story']}:</b><br>{html.escape(memo['story'])}")
        if memo["composition"]:
            memo_parts.append(f"<b>{MEMO_FIELDS['memo_input_composition']}:</b><br>{html.escape(memo['composition'])}")
        if memo["music"]:
            memo_parts.append(f"<b>{MEMO_FIELDS['memo_input_music']}:</b><br>{html.escape(memo['music'])}")
        if memo["cut"]:
            memo_parts.append(f"<b>{MEMO_FIELDS['memo_input_cut']}:</b><br>{html.escape(memo['cut'])}")
        if memo["color"]:
            memo_parts.append(f"<b>{MEMO_FIELDS['memo_input_color']}:</b><br>{html.escape(memo['color'])}")

        html_content += "<br><br>".join(memo_parts)
        # ------------------------------------------

        html_content += """
            </div>
        </div>
        """
    
    html_content += "</body></html>"
    return html_content

# --- コールバック関数: メモ削除 ---
def delete_memo(index):
    if 0 <= index < len(st.session_state.memos):
        st.session_state.memos.pop(index)

# --- ショットタイマー用のコールバック関数 ---
def start_shot_timer():
    """ショットタイマーを開始します。"""
    st.session_state.is_shot_timing = True
    st.session_state.shot_start_time = datetime.now()

# --- ★ショットタイマー停止 (変更点) ---
def stop_shot_timer_and_update_memo():
    """タイマーを停止し、計測結果を「ショットの構図」欄に追記します。"""
    if st.session_state.shot_start_time:
        shot_duration = datetime.now() - st.session_state.shot_start_time
        duration_str = f"（計測したショット長: {shot_duration.total_seconds():.1f} 秒）"
        
        # --- ★(変更点) 「ショットの構図」のキーを対象にする ---
        key_to_update = "memo_input_composition"
        current_text = st.session_state.get(key_to_update, "")
        
        if current_text:
            st.session_state[key_to_update] = f"{current_text}\n{duration_str}"
        else:
            st.session_state[key_to_update] = duration_str
        # -----------------------------------------------
            
    st.session_state.is_shot_timing = False
    st.session_state.shot_start_time = None

# --- コールバック関数: リセット ---
def reset_all():
    """状態をすべてリセットします。"""
    initialize_state(clear_memos=True)
    # テキストエリアも明示的にリセット
    for key in MEMO_FIELDS.keys():
        st.session_state[key] = ""

# --- ★「メモを記録」ボタン用のコールバック関数 (変更点) ---
def add_memo():
    """現在の5つのテキストエリアの内容を1つのメモとして追加します。"""
    
    # 5つの入力欄からテキストを読み込む
    memo_data = {}
    for key, label in MEMO_FIELDS.items():
        # 'memo_input_story' から 'story' というキーを作成
        simple_key = key.replace("memo_input_", "") 
        memo_data[simple_key] = st.session_state[key]

    # どれか1つでも入力があるかチェック
    if any(memo_data.values()):
        timestamp_str = format_timedelta(get_elapsed_time())
        new_id = st.session_state.memo_id_counter
        st.session_state.memo_id_counter += 1
        
        # タイムスタンプとIDをメモデータに追加
        memo_to_save = {
            "id": new_id,
            "time": timestamp_str,
            **memo_data # 5つのメモ項目を展開して追加
        }
        
        st.session_state.memos.append(memo_to_save)
        
        # テキストエリアをクリア
        for key in MEMO_FIELDS.keys():
            st.session_state[key] = ""
    else:
        st.warning("メモ内容（いずれかの項目）を入力してください。")

# --- 一時停止・再開用のコールバック関数 ---
def toggle_pause():
    if st.session_state.is_paused:
        # --- 再開処理 ---
        st.session_state.is_paused = False
        pause_duration = datetime.now() - st.session_state.pause_start_time
        st.session_state.paused_duration += pause_duration
        st.session_state.pause_start_time = None
    else:
        # --- 一時停止処理 ---
        st.session_state.is_paused = True
        st.session_state.pause_start_time = datetime.now()
        
        # 一時停止時にショットタイマーが動いていたら、強制的に停止＆記録
        if st.session_state.is_shot_timing:
            stop_shot_timer_and_update_memo()

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

    # --- 視聴コントロール ---
    if st.session_state.start_time is None:
        # 1. 視聴開始前
        if col1.button("▶️ 視聴開始", use_container_width=True, type="primary"):
            initialize_state(clear_memos=False) 
            st.session_state.start_time = datetime.now()
            st.rerun() 
    else:
        # 2. 視聴開始後
        if st.session_state.is_paused:
            # 3. 一時停止中
            col1.button("▶️ 再開", use_container_width=True, on_click=toggle_pause, type="primary")
        else:
            # 4. 視聴中
            col1.button("⏸️ 一時停止", use_container_width=True, on_click=toggle_pause)

    if col2.button("🔄 リセット", use_container_width=True, on_click=reset_all):
        pass # on_click が自動で rerun する


    if not st.session_state.start_time:
        st.info("映画のタイトルを入力し、「視聴開始」ボタンを押してください。")
    else:
        elapsed_time = get_elapsed_time()
        status_text = "（一時停止中）" if st.session_state.is_paused else "（視聴中）"
        st.info(f"経過時間: {format_timedelta(elapsed_time)}\n\n{status_text}")

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
st.header(f" 「{st.session_state.movie_title or '（タイトル未設定）'}」のメモ")

# --- 一時停止中は入力フォームを隠す ---
if st.session_state.start_time and not st.session_state.is_paused:
    
    st.subheader("⏱ ショットタイマー")
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
            help="このボタンを押すと計測を停止し、結果を「ショットの構図」欄に追記します。"
        )

    st.divider() 

    st.subheader(" メモを追加")
    
    # --- ★(変更点) 5つの入力欄を表示 ---
    st.text_area(
        MEMO_FIELDS["memo_input_story"], 
        key="memo_input_story", 
        placeholder="プロット、伏線、テーマなど..."
    )
    st.text_area(
        MEMO_FIELDS["memo_input_composition"], 
        key="memo_input_composition", 
        placeholder="ライティング、カメラアングル、フレーミングなど...",
        help="ショットタイマーの結果はここに追記されます。"
    )
    st.text_area(
        MEMO_FIELDS["memo_input_music"], 
        key="memo_input_music", 
        placeholder="BGM、効果音、無音の演出など..."
    )
    st.text_area(
        MEMO_FIELDS["memo_input_cut"], 
        key="memo_input_cut", 
        placeholder="カットの長さ、トランジション、編集のリズムなど..."
    )
    st.text_area(
        MEMO_FIELDS["memo_input_color"], 
        key="memo_input_color", 
        placeholder="キーカラー、色彩心理、フィルタなど..."
    )
    # -----------------------------------

    st.button(
        "📝 メモを記録",
        on_click=add_memo,
        type="primary",
        use_container_width=True,
        help="上記5つの欄の内容を、現在のタイムスタンプで1つのメモとして記録します。"
    )

    st.divider()

elif st.session_state.start_time and st.session_state.is_paused:
    st.info("（一時停止中です。サイドバーの「▶️ 再開」ボタンを押すとメモを再開できます。）")
    st.divider()
# -----------------------------------
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
            # --- ★(変更点) 5項目の内容を表示 ---
            has_content = False
            if memo["story"]:
                st.markdown(f"**{MEMO_FIELDS['memo_input_story']}:**")
                st.write(memo["story"])
                has_content = True
            if memo["composition"]:
                st.markdown(f"**{MEMO_FIELDS['memo_input_composition']}:**")
                st.write(memo["composition"])
                has_content = True
            if memo["music"]:
                st.markdown(f"**{MEMO_FIELDS['memo_input_music']}:**")
                st.write(memo["music"])
                has_content = True
            if memo["cut"]:
                st.markdown(f"**{MEMO_FIELDS['memo_input_cut']}:**")
                st.write(memo["cut"])
                has_content = True
            if memo["color"]:
                st.markdown(f"**{MEMO_FIELDS['memo_input_color']}:**")
                st.write(memo["color"])
                has_content = True
            
            if not has_content:
                st.write("（空のメモです）")
            # ------------------------------------