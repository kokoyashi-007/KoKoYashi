import streamlit as st
from datetime import datetime, timedelta
import html # ★HTMLエスケープのためにインポート

# --- アプリの基本設定 ---
st.set_page_config(layout="wide", page_title="映画鑑賞メモツール")

# --- ★状態管理の共通化 (スマート化 ①) ---
# --- コードの役割説明 ---
# 'initialize_state(clear_memos=False)'
# st.session_state の変数を初期化する関数です。
# リセットボタンが押されたときや、初回起動時に呼ばれます。
# これにより、初期化とリセットのロジックを一元管理できます。
# ------------------------
def initialize_state(clear_memos=False):
    """セッションステートを初期化またはリセットします。"""
    if 'start_time' not in st.session_state or clear_memos:
        st.session_state.start_time = None
    if 'movie_title' not in st.session_state or clear_memos:
        st.session_state.movie_title = ""
    if 'memos' not in st.session_state or clear_memos:
        st.session_state.memos = []
    if 'is_paused' not in st.session_state or clear_memos:
        st.session_state.is_paused = False
    if 'paused_duration' not in st.session_state or clear_memos:
        st.session_state.paused_duration = timedelta(0)
    if 'pause_start_time' not in st.session_state or clear_memos:
        st.session_state.pause_start_time = None
    # --- ★堅牢なID採番 (スマート化 ②) ---
    if 'memo_id_counter' not in st.session_state or clear_memos:
        st.session_state.memo_id_counter = 0
    
    # --- ★ショットタイマー用の状態を追加 ---
    if 'is_shot_timing' not in st.session_state or clear_memos:
        st.session_state.is_shot_timing = False
    if 'shot_start_time' not in st.session_state or clear_memos:
        st.session_state.shot_start_time = None

# --- セッションステートの初期化（初回実行時のみ） ---
initialize_state(clear_memos=False)

# --- ヘルパー関数: 経過時間をフォーマット ---
def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# --- ★経過時間計算を関数化 (スマート化 ③) ---
# --- コードの役割説明 ---
# 'get_elapsed_time()'
# 現在の有効な経過時間（一時停止時間を除いた時間）を計算して返す関数です。
# 複数の場所で使う計算ロジックを一つにまとめました。
# ------------------------
def get_elapsed_time():
    """一時停止を考慮した現在の経過時間を計算します。"""
    if not st.session_state.start_time:
        return timedelta(0)
    
    if st.session_state.is_paused:
        # 一時停止中の場合
        return (st.session_state.pause_start_time - st.session_state.start_time) - st.session_state.paused_duration
    else:
        # 再生中の場合
        return (datetime.now() - st.session_state.start_time) - st.session_state.paused_duration

# --- ★マークダウン生成 → HTML生成に変更 ---
def generate_html(title, memos):
    """メモのリストからHTMLファイルを生成します。"""
    
    # HTMLのヘッダーと基本的なスタイル
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{html.escape(title or '映画鑑賞メモ')}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; margin: 2em; background-color: #f9f9f9; }}
            .container {{ max-width: 800px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
            h1 {{ color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
            .memo {{ border-bottom: 1px solid #eee; padding: 15px 0; }}
            .memo:last-child {{ border-bottom: none; }}
            .time {{ font-size: 1.2em; font-weight: bold; color: #007bff; margin-bottom: 8px; }}
            .text {{ white-space: pre-wrap; /* 改行をそのまま表示 */ color: #555; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>「{html.escape(title or '（タイトル未設定）')}」のメモ</h1>
    """
    
    if not memos:
        html_content += "<p>メモはありません。</p>"
    else:
        # メモを時系列（古い順）で書き出す
        for memo in memos:
            # テキストを安全にHTML化し、改行を <br> タグに変換
            safe_text = html.escape(memo["text"]).replace('\n', '<br>')
            
            html_content += f"""
            <div class="memo">
                <div class="time">{memo['time']}</div>
                <div class="text">{safe_text}</div>
            </div>
            """
            
    html_content += """
        </div>
    </body>
    </html>
    """
    return html_content

# --- コールバック関数: メモ削除 ---
def delete_memo(index):
    if 0 <= index < len(st.session_state.memos):
        st.session_state.memos.pop(index)

# --- ★ショットタイマー用のコールバック関数を追加 ---
def start_shot_timer():
    """ショットタイマーを開始します。"""
    st.session_state.is_shot_timing = True
    st.session_state.shot_start_time = datetime.now()

def stop_shot_timer_and_add_memo():
    """ショットタイマーを停止し、結果をメモに追加します。"""
    if st.session_state.shot_start_time:
        shot_duration = (datetime.now() - st.session_state.shot_start_time).total_seconds()
        
        # メインタイマーの経過時間を取得
        timestamp_str = format_timedelta(get_elapsed_time())
        
        # メモのテキストを生成
        memo_text = f"【ショット計測】\n長さ: {shot_duration:.1f} 秒"
        
        # メモを追加
        new_id = st.session_state.memo_id_counter
        st.session_state.memo_id_counter += 1
        st.session_state.memos.append({
            "id": new_id,
            "time": timestamp_str,
            "text": memo_text,
        })

    st.session_state.is_shot_timing = False
    st.session_state.shot_start_time = None


# --- ★コールバック関数: リセット (スマート化 ①) ---
def reset_all():
    """状態をすべてリセットします。"""
    initialize_state(clear_memos=True) # 共通関数を呼び出す

# --- サイドバー (設定エリア) ---
with st.sidebar:
    st.header("🎬 映画鑑賞設定")
    
    # --- コードの役割説明 ---
    # 'st.text_input("映画のタイトル", ...)'
    # ユーザーが映画のタイトルを入力するためのテキストボックスを表示します。
    # 入力された内容は 'st.session_state.movie_title' に保存されます。
    # ------------------------
    st.session_state.movie_title = st.text_input(
        "映画のタイトル", 
        st.session_state.movie_title,
        placeholder="例: ショーシャンクの空に"
    )

    # --- ★視聴コントロールのロジックを変更 ---
    col1, col2 = st.columns(2)

    if st.session_state.start_time is None:
        # --- 1. 視聴開始前 ---
        if col1.button("▶️ 視聴開始", use_container_width=True, type="primary"):
            st.session_state.start_time = datetime.now()
            # リセットロジックの主要部分を initialize_state に移譲
            initialize_state(clear_memos=False) # タイトル以外をリセット
            st.session_state.start_time = datetime.now() # 開始時刻だけセット
            st.success(f"「{st.session_state.movie_title}」の視聴を開始しました。")
            st.rerun() # 状態を即時反映

    else:
        # --- 2. 視聴開始後 ---
        if st.session_state.is_paused:
            # --- 2a. 一時停止中 ---
            if col1.button("▶️ 再開", use_container_width=True, type="primary"):
                # 一時停止していた時間を加算
                pause_elapsed = datetime.now() - st.session_state.pause_start_time
                st.session_state.paused_duration += pause_elapsed
                st.session_state.is_paused = False
                st.session_state.pause_start_time = None
                st.rerun()
        else:
            # --- 2b. 再生中 ---
            if col1.button("⏸️ 一時停止", use_container_width=True):
                st.session_state.is_paused = True
                st.session_state.pause_start_time = datetime.now()
                st.rerun()

    # リセットボタンは常に表示（ただし開始後のみ意味がある）
    if col2.button("🔄 リセット", use_container_width=True, on_click=reset_all):
        st.info("リセットしました。")
        st.rerun()


    if not st.session_state.start_time:
        st.info("映画のタイトルを入力し、「視聴開始」ボタンを押してください。")
    else:
        # --- ★経過時間の計算ロジックを共通関数に変更 (スマート化 ③) ---
        elapsed_time = get_elapsed_time()
        
        if st.session_state.is_paused:
            st.warning(f"一時停止中\n\n経過時間: {format_timedelta(elapsed_time)}")
        else:
            st.info(f"視聴開始: {st.session_state.start_time.strftime('%H:%M:%S')}\n\n経過時間: {format_timedelta(elapsed_time)}")

    # --- ★メモ保存機能を追加 ---
    if st.session_state.memos:
        st.divider()
        
        # --- ★HTMLデータを生成するように変更 ---
        html_data = generate_html(
            st.session_state.movie_title,
            st.session_state.memos
        )
        
        # --- コードの役割説明 ---
        # 'st.download_button(...)'
        # --- ★HTMLをダウンロードするように変更 ---
        st.download_button(
            label="📁 メモを保存 (.html)", # ラベル変更
            data=html_data,
            file_name=f"{st.session_state.movie_title or 'movie_memo'}_{datetime.now().strftime('%Y%m%d')}.html", # 拡張子変更
            mime="text/html", # MIMEタイプ変更
            use_container_width=True,
            help="現在のすべてのメモをHTMLファイルとしてダウンロードします。" # ヘルプテキスト変更
        )


# --- メインエリア (入力 & メモ表示エリア) ---
st.header(f"🗒️ 「{st.session_state.movie_title or '（タイトル未設定）'}」のメモ")

# --- ★一時停止中は入力フォームを非表示に変更 ---
if st.session_state.start_time and not st.session_state.is_paused:
    
    # --- ★ショットタイマーUIを追加 ---
    st.subheader("ショットタイマー")
    if not st.session_state.is_shot_timing:
        # --- コードの役割説明 ---
        # 'st.button("🎬 ショット計測開始", ...)'
        # ショットタイマーを開始するためのボタンです。
        # 押されると on_click で 'start_shot_timer' 関数が呼ばれます。
        # ------------------------
        st.button(
            "🎬 ショット計測開始",
            on_click=start_shot_timer,
            use_container_width=True,
            help="このボタンを押した時点からショットの長さの計測を開始します。"
        )
    else:
        # 計測中の秒数を計算
        elapsed_shot_time = (datetime.now() - st.session_state.shot_start_time).total_seconds()
        
        # --- コードの役割説明 ---
        # 'st.button(f"⏹️ 計測停止...", ...)'
        # ショットタイマーを停止するためのボタンです。
        # 押されると on_click で 'stop_shot_timer_and_add_memo' 関数が呼ばれます。
        # ------------------------
        st.button(
            f"⏹️ 計測停止 (現在 {elapsed_shot_time:.1f} 秒)",
            on_click=stop_shot_timer_and_add_memo,
            use_container_width=True,
            type="primary",
            help="このボタンを押すと計測を停止し、結果を自動的にメモ一覧に追加します。"
        )

    st.divider() # ショットタイマーと手動メモ入力の間に区切り線

    with st.form(key="memo_form", clear_on_submit=True):
        st.subheader("メモを追加")
        
        # --- コードの役割説明 ---
        # 'st.text_area(...)'
        # メモ内容を入力するための複数行テキストエリアです。
        # ------------------------
        current_memo_text = st.text_area("気になったこと、伏線など", key="current_memo_text_area")

        # --- コードの役割説明 ---
        # 'st.form_submit_button("メモを記録")'
        # フォーム内の入力を送信（記録）するためのボタンです。
        # ------------------------
        submitted = st.form_submit_button("📝 メモを記録")
        
        if submitted:
            if current_memo_text:
                # --- ★経過時間の計算ロジックを共通関数に変更 (スマート化 ③) ---
                timestamp_str = format_timedelta(get_elapsed_time())
                
                # --- ★ID採番方法を変更 (スマート化 ②) ---
                new_id = st.session_state.memo_id_counter
                st.session_state.memo_id_counter += 1 # カウンターを進める
                
                # メモをリストに追加
                st.session_state.memos.append({
                    "id": new_id, # 堅牢なID
                    "time": timestamp_str,
                    "text": current_memo_text,
                })
                
            else:
                st.warning("メモ内容を入力してください。")

    st.divider() # 入力欄とメモ一覧の間に区切り線

elif st.session_state.start_time and st.session_state.is_paused:
    st.info("（一時停止中です。サイドバーの「▶️ 再開」ボタンを押すとメモを再開できます。）")

else:
    st.info("サイドバーから視聴を開始すると、ここにメモが記録されます。")

if not st.session_state.memos and st.session_state.start_time:
    st.info("まだメモはありません。メインエリアのフォームから最初のメモを記録しましょう。")

# --- コードの役割説明 ---
# 'st.session_state.memos'
# 保存されたメモのリストを逆順（新しい順）にループ処理で表示します。
# ------------------------
for i, memo in enumerate(reversed(st.session_state.memos)):
    # リストを逆順にしているので、元のリストでのインデックスを計算
    original_index = len(st.session_state.memos) - 1 - i
    
    # --- コードの役割説明 ---
    # 'st.container(border=True)'
    # 各メモを枠線付きのコンテナで囲み、見やすくします。
    # ------------------------
    with st.container(border=True):
        col1, col2 = st.columns([1, 4])
        
        with col1:
            # --- コードの役割説明 ---
            # 'st.metric(...)'
            # 記録された時間（経過時間）を強調して表示します。
            # ------------------------
            st.metric(label="記録時間", value=memo["time"])
            
            # --- コードの役割説明 ---
            # 'st.button("削除", ...)'
            # ...
            # 'key' が 'id' に基づいているため、重複しないことが保証される
            # ------------------------
            st.button(
                "🗑️ 削除", 
                key=f"delete_{memo['id']}", # ★堅牢なIDを使用
                on_click=delete_memo, 
                args=(original_index,)
            )

        with col2:
            if memo["text"]:
                # --- コードの役割説明 ---
                # 'st.write(memo["text"])'
                # 記録されたメモのテキストを表示します。
                # ------------------------
                st.write(memo["text"])