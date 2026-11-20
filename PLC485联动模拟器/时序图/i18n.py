# -*- coding: utf-8 -*-
"""
时序图的日语 / 英语翻译表。render.py 出图时用它生成
  out/时序图_ja.drawio   日本語版
  out/时序图_en.drawio   English version

写法：每行 (中文原文, 日本語, English)。中文原文必须和 charts.py / render.py 里的字符串一模一样，
改了 charts.py 的文字就要在这里同步改（或加一行）。对不上的会在出图时列出来（「缺翻译」），
那几处先用中文顶着，同时写进 out/缺翻译.txt。

标记：
  中文 / 日语  【推】清洗机 / 温水器侧的前提  【IO】IO 分配  【P】本方案  【未】还没定  【定】已定
  英语         [I]  [IO]  [P]  [?]  [OK]

短帧（固定宽度，约 32 px）里的字要短：日语 ≤ 4 个全角字，英语 ≤ 7 个字母左右。
阶段名（表头）可以用 \n 指定在哪里换行，免得浏览器把「5 s」这种拆到两行。
"""

ENTRIES = [
    # ---------- 界面 ----------
    ('区分', '区分', 'Group'),
    ('信号', '信号', 'Signal'),
    ('备考', '備考', 'Notes'),
    ('这张图回答：', 'この図で答えること：', 'This chart answers: '),
    ('【注记】', '【注記】', '[Notes]'),
    ('表格', 'テーブル', 'Table'),
    ('标记：【推】清洗机 / 温水器侧的前提　【IO】IO 分配　【P】PLC 本方案　【未】还没定　【定】已定'
     '　｜　红虚线框「无」= 没应答',
     '凡例：【推】洗浄機・温水器側の前提　【IO】IO 割付　【P】PLC 本案　【未】未定　【定】確定'
     '　｜　赤破線枠「無」= 応答なし',
     'Legend: [I] cleaner / heater side premise   [IO] IO assignment   [P] this PLC proposal'
     '   [?] not decided   [OK] decided'
     '   |   red dashed box "none" = no reply'),

    # ---------- 分区 ----------
    ('清洗机内部\n（参考）', '洗浄機内部\n（参考）', 'Cleaner internal\n(reference)'),
    ('清洗机\n→ PLC', '洗浄機\n→ PLC', 'Cleaner\n→ PLC'),
    ('清洗机→温水器\n直连', '洗浄機→温水器\n直結', 'Cleaner→heater\ndirect'),
    ('PLC →\n清洗机', 'PLC →\n洗浄機', 'PLC →\ncleaner'),
    ('PLC →\n温水器', 'PLC →\n温水器', 'PLC →\nheater'),
    ('温水器\n→ PLC', '温水器\n→ PLC', 'Heater\n→ PLC'),
    ('温水器\n状态', '温水器\n状態', 'Heater\nstatus'),
    ('PLC\n内部', 'PLC\n内部', 'PLC\ninternal'),

    # ---------- 标题 ----------
    ('装置启动 → 等 30 s → 两边初始化', '装置起動 → 30 s 待ち → 双方の初期化',
     'Equipment start → wait 30 s → init on both sides'),
    ('装置结束：远程电源切断 → 停轮询', '装置終了：リモート電源遮断 → ポーリング停止',
     'Equipment end: remote power OFF → stop polling'),
    ('手动：投入开始 → 安定 → 投入停止', '手動：投入開始 → 安定 → 投入停止',
     'Manual: supply start → stable → supply stop'),
    ('自动：准备开始 → 等安定 → 投入 → 准备停止', '自動：準備開始 → 安定待ち → 投入 → 準備停止',
     'Auto: prep start → wait for stable → supply → prep stop'),
    ('两个轮询周期：清洗机 500 ms，PLC 3 s', '2 つのポーリング周期：洗浄機 500 ms、PLC 3 s',
     'Two polling cycles: cleaner 500 ms, PLC 3 s'),
    ('温水器报警 → 重故障 → 复位', '温水器アラーム → 重故障 → リセット',
     'Heater alarm → major fault → reset'),
    ('温水器侧断线 → PLC 切远程电源 → 复位', '温水器側断線 → PLC がリモート電源を遮断 → リセット',
     'Heater-side link loss → PLC cuts remote power → reset'),
    ('清洗机侧断线 → 复位', '洗浄機側断線 → リセット', 'Cleaner-side link loss → reset'),
    ('PLC 自己断电 / 停止 → 重启 → 复位', 'PLC 自身の電源断 / 停止 → 再起動 → リセット',
     'PLC itself loses power / stops → restart → reset'),

    # ---------- 这张图回答 ----------
    ('温水器上电后 30 s 不能通信，清洗机的初始化怎么过；PLC 什么时候开始和温水器通信',
     '温水器は通電後 30 s 通信できない。洗浄機の初期化をどう通すか／PLC はいつ温水器と通信を始めるか',
     "The heater can't communicate for 30 s after power-on: how does the cleaner's init pass, "
     "and when does the PLC start talking to the heater?"),
    ('温水器被直接断电时，PLC 怎么不把它当成断线',
     '温水器の電源が直接切られたとき、PLC がそれを断線と判定しないようにするには',
     "When the heater's power is cut directly, how does the PLC avoid treating it as a link loss?"),
    ('清洗机给运转、停运转时，PLC 往温水器发什么、按什么顺序；安定 DO 什么时候变',
     '洗浄機が運転 ON / OFF したとき、PLC は温水器に何をどの順で送るか／安定 DO はいつ変わるか',
     'When the cleaner turns run ON / OFF, what does the PLC send to the heater, in what order; '
     'when does the stable DO change?'),
    ('自动模式下清洗机等安定再投入，安定 DO 晚到会不会拖慢节拍',
     '自動モードでは洗浄機は安定を待ってから投入する。安定 DO が遅れるとタクトが延びるか',
     'In auto mode the cleaner waits for stable before supplying: does a late stable DO slow the cycle?'),
    ('清洗机读得勤、PLC 读得慢，中间怎么接；温水器状态变了，清洗机多久能看到',
     '洗浄機は頻繁に、PLC はゆっくり読む。間をどうつなぐか／温水器の状態変化が洗浄機に見えるまでの時間',
     'The cleaner polls often, the PLC slowly: how do they connect, and how soon does the cleaner '
     'see a heater status change?'),
    ('温水器自己报警时清洗机看到什么；复位信号的 5 s 里 PLC 要做完什么',
     '温水器がアラームを出したとき洗浄機に何が見えるか／リセット信号の 5 s の間に PLC が済ませること',
     'When the heater raises an alarm, what does the cleaner see; what must the PLC finish within '
     'the 5 s reset signal?'),
    ('PLC 和温水器之间断了，清洗机看到什么；PLC 怎么让温水器停下来；线修好以后怎么解除',
     'PLC–温水器間が断線したとき洗浄機に何が見えるか／PLC はどう温水器を止めるか／復旧後の解除方法',
     'If the PLC–heater link breaks: what does the cleaner see, how does the PLC stop the heater, '
     'and how is it cleared after repair?'),
    ('清洗机读写不到 PLC 时，谁让温水器停下来；线修好以后怎么解除',
     '洗浄機が PLC と読み書きできないとき、誰が温水器を止めるか／復旧後の解除方法',
     'When the cleaner cannot reach the PLC, who stops the heater, and how is it cleared after repair?'),
    ('PLC 断电或停止运行时，清洗机和温水器各会怎样；PLC 重新起来以后怎么恢复',
     'PLC が電源断・停止したとき洗浄機と温水器はそれぞれどうなるか／PLC 復帰後の復旧方法',
     'When the PLC loses power or stops, what happens to the cleaner and the heater; '
     'how does it recover when the PLC comes back?'),

    # ---------- 阶段 ----------
    ('装置启动', '装置起動', 'Equipment start'),
    ('温水器启动中（30 s）', '温水器起動中\n（30 s）', 'Heater booting (30 s)'),
    ('温水器起来 · PLC 初始化', '温水器起動完了・PLC 初期化', 'Heater up · PLC init'),
    ('待机（通水 ON / 运转 OFF）', '待機（通水 ON /\n運転 OFF）', 'Idle\n(flow ON / run OFF)'),
    ('待机', '待機', 'Idle'),
    ('装置结束（远程电源切断）', '装置終了\n（リモート電源遮断）', 'Equipment end (remote power OFF)'),
    ('温水器断电中', '温水器 電源断中', 'Heater unpowered'),
    ('下次装置启动（远程电源投入）', '次の装置起動\n（リモート電源投入）', 'Next equipment start (remote power ON)'),
    ('满 30 s · 恢复轮询', '30 s 経過・\nポーリング再開', '30 s passed · polling resumes'),
    ('投入开始', '投入開始', 'Supply start'),
    ('升温', '昇温', 'Heating up'),
    ('安定', '安定', 'Stable'),
    ('投入停止', '投入停止', 'Supply stop'),
    ('准备开始', '準備開始', 'Prep start'),
    ('运转 ON（延时后）', '運転 ON（遅延後）', 'Run ON\n(after delay)'),
    ('升温 → 安定', '昇温 → 安定', 'Heating up → stable'),
    ('准备停止', '準備停止', 'Prep stop'),
    ('0 s', '0 s', '0 s'),
    ('0.5 s', '0.5 s', '0.5 s'),
    ('1.0 s', '1.0 s', '1.0 s'),
    ('1.5 s', '1.5 s', '1.5 s'),
    ('2.0 s', '2.0 s', '2.0 s'),
    ('2.5 s', '2.5 s', '2.5 s'),
    ('3.0 s', '3.0 s', '3.0 s'),
    ('供水中', '温水供給中', 'Supplying'),
    ('温水器报警', '温水器アラーム', 'Heater alarm'),
    ('PLC 读到', 'PLC が検知', 'PLC detects'),
    ('清洗机停', '洗浄機停止', 'Cleaner stops'),
    ('原因消除', '原因解消', 'Cause removed'),
    ('复位 ON（约 5 s）', 'リセット ON\n（約 5 s）', 'Reset ON (~5 s)'),
    ('复位 OFF · 检查', 'リセット OFF・\nチェック', 'Reset OFF · check'),
    ('断线 · 超时 1', '断線・\nタイムアウト 1', 'Link lost · timeout 1'),
    ('超时 2', 'タイムアウト 2', 'Timeout 2'),
    ('超时 3 = 通信异常 · 切电源', 'タイムアウト 3 =\n通信異常・電源遮断', 'Timeout 3 = comm error · power cut'),
    ('线修好 · 装置再启动', '線復旧・装置再起動', 'Line fixed · equipment restart'),
    ('满 30 s · 恢复通信', '30 s 経過・通信再開', '30 s passed ·\ncomm resumes'),
    ('断线', '断線', 'Link lost'),
    ('清洗机读失败', '洗浄機 読出失敗', 'Cleaner reads fail'),
    ('PLC 判断线', 'PLC が断線判定', 'PLC detects\nlink loss'),
    ('线修好', '線復旧', 'Line fixed'),
    ('PLC 断电 / 停止', 'PLC 電源断 / 停止', 'PLC power off / stop'),
    ('清洗机看到故障 · 停', '洗浄機\n故障検知・停止', 'Cleaner sees\nfault · stops'),
    ('清洗机读报警失败', '洗浄機\nアラーム読出失敗', 'Cleaner alarm\nreads fail'),
    ('PLC 重新运行', 'PLC 運転再開', 'PLC runs again'),
    ('PLC 读温水器 · 补发停止', 'PLC 温水器読出・\n停止を再送', 'PLC reads heater · resends stop'),

    # ---------- 信号名 ----------
    ('远程电源投入', 'リモート電源投入', 'Remote power ON'),
    ('远程电源切断', 'リモート電源遮断', 'Remote power OFF'),
    ('远程电源', 'リモート電源', 'Remote power'),
    ('通水', '通水', 'Water flow'),
    ('写温度', '温度書込', 'Write temp'),
    ('读报警', 'アラーム読出', 'Read alarms'),
    ('写应答', '書込応答', 'Write reply'),
    ('读应答', '読出応答', 'Read reply'),
    ('状态读出', '状態読出', 'Status read'),
    ('写温度 · 读回', '温度書込・読み戻し', 'Write temp · readback'),
    ('应答', '応答', 'Reply'),
    ('控制电源', '制御電源', 'Control power'),
    ('可以通信', '通信可能', 'Comm ready'),
    ('设定温度（内部）', '設定温度（内部）', 'Setpoint (internal)'),
    ('启动等待', '起動待ち', 'Boot wait'),
    ('重故障 DO', '重故障 DO', 'Major fault DO'),
    ('轻故障 DO', '軽故障 DO', 'Minor fault DO'),
    ('轮询', 'ポーリング', 'Polling'),
    ('投入阀', '投入弁', 'Supply valve'),
    ('运转', '運転', 'Run'),
    ('温度安定 DO', '温度安定 DO', 'Temp stable DO'),
    ('温度', '温度', 'Temp'),
    ('状态读出 · 读回', '状態読出・読み戻し', 'Status read · readback'),
    ('运转 · 入口阀 · 加热', '運転・入口弁・加熱', 'Run · inlet valve · heat'),
    ('安定（内部）', '安定（内部）', 'Stable (internal)'),
    ('Out 侧排水阀', 'Out 側排水弁', 'Out-side drain valve'),
    ('启动 3 帧', '起動 3 フレーム', 'Start: 3 frames'),
    ('停止 3 帧', '停止 3 フレーム', 'Stop: 3 frames'),
    ('运转 / 通水', '運転 / 通水', 'Run / flow'),
    ('蜂鸣器复位', 'ブザーリセット', 'Buzzer reset'),
    ('复位', 'リセット', 'Reset'),
    ('读应答（报警 bit）', '読出応答（アラーム bit）', 'Read reply (alarm bits)'),
    ('报警详细', 'アラーム詳細', 'Alarm detail'),
    ('报警', 'アラーム', 'Alarm'),
    ('加热', '加熱', 'Heating'),
    ('失败次数', '失敗回数', 'Fail count'),
    ('通信异常', '通信異常', 'Comm error'),
    ('报警读取异常', 'アラーム読出異常', 'Alarm read error'),
    ('停止', '停止', 'Stop'),
    ('清洗机断线', '洗浄機断線', 'Cleaner link lost'),
    ('温度设定异常', '温度設定異常', 'Temp set error'),
    ('PLC 运行', 'PLC 動作', 'PLC state'),

    # ---------- 备考 ----------
    ('【IO】进 PLC，由 PLC 转给温水器', '【IO】PLC に入力、PLC から温水器へ転送', '[IO] into PLC; PLC passes it to the heater'),
    ('【推】装置启动就 ON；和远程电源投入同时【定】', '【推】装置起動で ON。リモート電源投入と同時【定】',
     '[I] ON at equipment start; same time as remote power ON [OK]'),
    ('【推】初始化写 25.0，没应答重试 3 次', '【推】初期化で 25.0 を書込、無応答なら 3 回リトライ',
     '[I] init writes 25.0; no reply → 3 retries'),
    ('【推】初始化成功后周期读（500 ms）', '【推】初期化成功後に周期読出（500 ms）', '[I] cyclic read after init (500 ms)'),
    ('【P】Modbus 从站收到就回，25.0 先存着', '【P】Modbus スレーブは受信即応答、25.0 は保持',
     '[P] Modbus slave replies at once; 25.0 is stored'),
    ('【P】用缓存回答；温水器起来之前回全 0', '【P】キャッシュで応答。温水器の起動前は全 0',
     '[P] answers from cache; all 0 until the heater is up'),
    ('【IO】PLC 转发（IO 输出）', '【IO】PLC が転送（IO 出力）', '[IO] PLC forwards (IO output)'),
    ('【推】等满 30 s 才发；第一次查是不是串口模式【P】', '【推】30 s 経過後に送信。初回はシリアルモードか確認【P】',
     '[I] sent only after 30 s; first reply checks serial mode [P]'),
    ('【P】转发 25.0，再读回核对【推】', '【P】25.0 を転送し、読み戻して照合【推】',
     '[P] forwards 25.0, then reads back to verify [I]'),
    ('【推】ACK / 状态应答', '【推】ACK / 状態応答', '[I] ACK / status reply'),
    ('【推】PLC 转发投入时上电', '【推】PLC が投入を転送した時に通電', '[I] powered when the PLC forwards power ON'),
    ('【推】上电 30 s 以后', '【推】通電 30 s 後',
     '[I] 30 s after power-on'),
    ('【P】转发远程电源投入时起计 30 s', '【P】リモート電源投入の転送時から 30 s 計時',
     '[P] 30 s timer starts when power ON is forwarded'),
    ('【IO】同上', '【IO】同上', '[IO] same as above'),
    ('【推】和远程电源同时 OFF / ON【定】', '【推】リモート電源と同時に OFF / ON【定】',
     '[I] OFF / ON together with remote power [OK]'),
    ('【P】切断以后不判通信异常', '【P】遮断後は通信異常と判定しない', '[P] no comm-error check after power OFF'),
    ('【IO】PLC 转发', '【IO】PLC が転送', '[IO] PLC forwards'),
    ('【P】转发切断就停；转发投入后等 30 s 再发', '【P】遮断の転送で停止。投入の転送後 30 s 待って再開',
     '[P] stops when OFF is forwarded; resumes 30 s after ON'),
    ('【推】', '【推】', '[I]'),
    ('【推】跟 PLC 转发走', '【推】PLC の転送に従う', '[I] follows what the PLC forwards'),
    ('【推】上电 30 s 以后', '【推】通電 30 s 後', '[I] 30 s after power-on'),
    ('【P】', '【P】', '[P]'),
    ('【推】投入开始开，投入停止后延时关；不等安定', '【推】投入開始で開、投入停止後に遅延して閉。安定を待たない',
     '[I] opens at supply start, closes after a delay at stop; no wait for stable'),
    ('【推】装置启动起一直 ON', '【推】装置起動からずっと ON', '[I] ON from equipment start onward'),
    ('【推】投入开始 ON / 投入停止 OFF', '【推】投入開始で ON / 投入停止で OFF', '[I] ON at supply start / OFF at supply stop'),
    ('【推】和运转同时写', '【推】運転と同時に書込', '[I] written together with run'),
    ('【P】Modbus 从站收到就回（几 ms），值存进缓存', '【P】Modbus スレーブが即応答（数 ms）、値はキャッシュへ',
     '[P] Modbus slave replies at once (a few ms); value goes to cache'),
    ('【P】状态读出 / 读回读到才变', '【P】状態読出 / 読み戻しで読めた時に変化',
     '[P] changes only when a status read / readback sees it'),
    ('【推】ON / OFF（①②③ = 发送顺序）', '【推】ON / OFF（①②③ = 送信順）', '[I] ON / OFF (①②③ = send order)'),
    ('【推】单位 0.1 ℃', '【推】単位 0.1 ℃', '[I] unit 0.1 °C'),
    ('【推】ON / OFF', '【推】ON / OFF', '[I] ON / OFF'),
    ('【推】3 s 一次；发完马上读回核对', '【推】3 s 周期。送信後すぐ読み戻して照合',
     '[I] every 3 s; read back right after sending'),
    ('【推】运转 OFF 就掉（待确认）', '【推】運転 OFF で落ちる（要確認）',
     '[I] drops when run turns OFF (TBC)'),
    ('【推】准备开始开 / 投入开始延时后关 / 投入停止开 / 准备停止延时后关',
     '【推】準備開始で開 / 投入開始の遅延後に閉 / 投入停止で開 / 準備停止の遅延後に閉',
     '[I] open at prep start / close after delay at supply start / open at supply stop / '
     'close after delay at prep stop'),
    ('【推】【定】等安定 ON 才进投入开始；投入停止延时后关', '【推】【定】安定 ON を待って投入開始。投入停止の遅延後に閉',
     '[I][OK] supply starts only after stable ON; closes after a delay at stop'),
    ('【推】准备开始延时后 ON / 准备停止 OFF', '【推】準備開始の遅延後に ON / 準備停止で OFF',
     '[I] ON after a delay at prep start / OFF at prep stop'),
    ('【P】① 通水 → ② 温度 → ③ 运转', '【P】① 通水 → ② 温度 → ③ 運転', '[P] ① flow → ② temp → ③ run'),
    ('【P】① 温度 → ② 运转 OFF → ③ 通水 OFF', '【P】① 温度 → ② 運転 OFF → ③ 通水 OFF',
     '[P] ① temp → ② run OFF → ③ flow OFF'),
    ('【推】3 s 一次；发完 3 帧马上读回', '【推】3 s 周期。3 フレーム送信後すぐ読み戻し',
     '[I] every 3 s; read back right after the 3 frames'),
    ('【推】周期读，500 ms', '【推】周期読出、500 ms', '[I] cyclic read, 500 ms'),
    ('【P】直接用缓存回答，不等温水器', '【P】キャッシュで即応答、温水器を待たない',
     '[P] answers from cache, does not wait for the heater'),
    ('【P】缓存更新时刷新', '【P】キャッシュ更新時に反映', '[P] updated when the cache updates'),
    ('【推】3 s 一次', '【推】3 s 周期', '[I] every 3 s'),
    ('【推】【未】收到重故障后 OFF（见 ※6）', '【推】【未】重故障を受けて OFF（※6 参照）',
     '[I][?] OFF after a major fault (see ※6)'),
    ('【未】停的时候写 25.0', '【未】停止時に 25.0 を書込', '[?] writes 25.0 when stopping'),
    ('【IO】单独的输入信号', '【IO】独立した入力信号', '[IO] separate input signal'),
    ('【推】画面解除 → ON 约 5 s → OFF', '【推】画面解除 → 約 5 s ON → OFF', '[I] reset on screen → ON ~5 s → OFF'),
    ('【推】「停止错误」位 → 重故障【P】；复位后补读到清除才 OFF',
     '【推】「停止エラー」bit → 重故障【P】。リセット後の再読出で解除を確認して OFF',
     '[I] "stop error" bit → major fault [P]; OFF only when the re-read after reset shows it cleared'),
    ('【推】两边报警编号相同，按编号直接换算', '【推】両側のアラーム番号は同じ、番号で直接変換',
     '[I] same alarm numbers on both sides; mapped directly by number'),
    ('【推】蜂鸣器复位 IO → 蜂鸣；复位 IO → 错误 + 蜂鸣【P】',
     '【推】ブザーリセット IO → ブザー。リセット IO → エラー + ブザー【P】',
     '[I] buzzer reset IO → buzzer; reset IO → error + buzzer [P]'),
    ('【推】3 s；发完马上读回；复位后马上补一次【P】', '【推】3 s。送信後すぐ読み戻し。リセット後すぐ 1 回追加【P】',
     '[I] 3 s; read back after sending; one extra read right after reset [P]'),
    ('【P】状态里错误位亮了才读', '【P】状態のエラー bit が立った時だけ読む',
     '[P] read only when an error bit is set in status'),
    ('【推】停止类报警，原因消除后也锁着', '【推】停止系アラーム、原因解消後もラッチ',
     '[I] stop-type alarm stays latched after the cause clears'),
    ('【推】停止类报警时自己停', '【推】停止系アラームで自ら停止', '[I] stops by itself on a stop-type alarm'),
    ('【推】收到重故障后 OFF', '【推】重故障を受けて OFF', '[I] OFF after a major fault'),
    ('【推】【未】收到重故障后 OFF；装置启动时 ON', '【推】【未】重故障を受けて OFF。装置起動時に ON',
     '[I][?] OFF after a major fault; ON at equipment start'),
    ('【IO】装置再启动（之前的切断省略）', '【IO】装置再起動（その前の遮断は省略）',
     '[IO] equipment restart (the earlier OFF is omitted)'),
    ('【未】停的时候写 25.0；【推】启动时初始化写 25.0', '【未】停止時に 25.0 を書込。【推】起動時の初期化で 25.0 を書込',
     '[?] writes 25.0 when stopping; [I] init writes 25.0 at start'),
    ('【P】通信异常锁存；复位且通信正常才 OFF', '【P】通信異常をラッチ。リセットかつ通信正常で OFF',
     '[P] comm error latched; OFF only on reset with comm OK'),
    ('【P】通信异常时 OFF', '【P】通信異常時に OFF', '[P] OFF on comm error'),
    ('【P】断线期间照常应答清洗机', '【P】断線中も洗浄機には通常どおり応答', '[P] keeps answering the cleaner during the link loss'),
    ('【P】从站马上回，值先存着', '【P】スレーブが即応答、値は保持', '[P] slave replies at once; value stored'),
    ('【P】通信异常 → 自己切一次（已定）；投入是转发【IO】', '【P】通信異常 → 自ら 1 回遮断（決定済）。投入は転送【IO】',
     '[P] comm error → PLC cuts once by itself (decided); ON is forwarded [IO]'),
    ('【推】超时 1000 ms，重试 3 次；切电源后停；复位后补读【P】',
     '【推】タイムアウト 1000 ms、リトライ 3 回。電源遮断後は停止。リセット後に再読出【P】',
     '[I] timeout 1000 ms, 3 retries; stops after the power cut; re-read after reset [P]'),
    ('【P】起来后转发缓存里的温度', '【P】起動後にキャッシュの温度を転送', '[P] forwards the cached temp once the heater is up'),
    ('【P】错误复位 + 蜂鸣器复位；线忙就等读回完再发', '【P】エラーリセット + ブザーリセット。回線使用中は読み戻し完了後に送信',
     '[P] error reset + buzzer reset; if the line is busy, sent after the readback'),
    ('【推】没有通信看门狗；断电才停', '【推】通信ウォッチドッグなし。電源断でのみ停止',
     '[I] no comm watchdog; stops only on power loss'),
    ('【P】超时那一刻 +1', '【P】タイムアウトの瞬間に +1', '[P] +1 at the moment of timeout'),
    ('【P】复位且通信正常才清', '【P】リセットかつ通信正常で解除', '[P] cleared only on reset with comm OK'),
    ('【P】转发投入起计 30 s', '【P】投入の転送から 30 s 計時', '[P] 30 s from forwarding power ON'),
    ('【推】读失败 3 次报警，只显示不停机；画面无条件解除', '【推】読出失敗 3 回でアラーム、表示のみで停止しない。画面で無条件解除',
     '[I] alarm after 3 failed reads, display only (no stop); cleared on screen unconditionally'),
    ('【推】500 ms；没应答时等超时再读', '【推】500 ms。無応答ならタイムアウト後に次の読出',
     '[I] 500 ms; on no reply, the next read comes after the timeout'),
    ('【P】判断线后锁存，复位后补读正常才 OFF', '【P】断線判定でラッチ。リセット後の再読出が正常なら OFF',
     '[P] latched on link loss; OFF when the re-read after reset is OK'),
    ('【P】判断线时 OFF', '【P】断線判定時に OFF', '[P] OFF when the link loss is detected'),
    ('【P】运转 OFF → 通水 OFF', '【P】運転 OFF → 通水 OFF', '[P] run OFF → flow OFF'),
    ('【P】发完马上读回；复位后补读', '【P】送信後すぐ読み戻し。リセット後に再読出', '[P] read back after sending; re-read after reset'),
    ('【P】错误复位 + 蜂鸣器复位', '【P】エラーリセット + ブザーリセット', '[P] error reset + buzzer reset'),
    ('【未】约 5 s 没收到请求就判（暂定）；收到请求就清', '【未】約 5 s 要求が来なければ判定（暫定）。要求を受けたら解除',
     '[?] detected after ~5 s without requests (tentative); cleared on the next request'),
    ('【推】写温度失败 3 次 → 循环停止、温水停止', '【推】温度書込失敗 3 回 → サイクル停止・温水停止',
     '[I] 3 failed temp writes → cycle stop, hot water stop'),
    ('【推】读报警失败 3 次 → 只显示', '【推】アラーム読出失敗 3 回 → 表示のみ', '[I] 3 failed alarm reads → display only'),
    ('【推】看到重故障后 OFF', '【推】重故障を見て OFF', '[I] OFF on seeing the major fault'),
    ('【推】停的时候写 25.0', '【推】停止時に 25.0 を書込', '[I] writes 25.0 when stopping'),
    ('【P】PLC 停着，没有应答', '【P】PLC 停止中、応答なし', '[P] PLC stopped, no reply'),
    ('【P】重启后回「报警」，复位后清零', '【P】再起動後は「アラーム」を返し、リセットでクリア',
     '[P] replies "alarm" after restart; cleared by reset'),
    ('【P】b 接点：PLC 停 = 接点断开 = 报警；重启后保持到复位', '【P】b接点：PLC 停止 = 接点開 = アラーム。再起動後もリセットまで保持',
     '[P] NC contact: PLC stop = contact open = alarm; held after restart until reset'),
    ('【P】b 接点：同上', '【P】b接点：同上', '[P] NC contact: same as above'),
    ('【P】PLC 停 = OFF', '【P】PLC 停止 = OFF', '[P] PLC stop = OFF'),
    ('【推】3 s 一次；重启后先读一次；发完读回；复位后补读【P】',
     '【推】3 s 周期。再起動後まず 1 回読出、送信後に読み戻し、リセット後に再読出【P】',
     '[I] every 3 s; one read after restart; read back after sending; re-read after reset [P]'),
    ('【P】按清洗机当前要求补发：25.0 → 运转 OFF → 通水 OFF', '【P】洗浄機の現在の要求どおり再送：25.0 → 運転 OFF → 通水 OFF',
     "[P] resent per the cleaner's current request: 25.0 → run OFF → flow OFF"),
    ('【推】没有看门狗，PLC 停了也继续', '【推】ウォッチドッグなし、PLC が止まっても継続',
     '[I] no watchdog; keeps going even if the PLC stops'),

    # ---------- 色块里的字 ----------
    ('ON', 'ON', 'ON'),
    ('25.0', '25.0', '25.0'),
    ('50.0', '50.0', '50.0'),
    ('读', '読', 'Read'),
    ('ACK', 'ACK', 'ACK'),
    ('全 0', '全 0', 'All 0'),
    ('缓存', 'キャッシュ', 'Cache'),
    ('新缓存', '新値', 'New'),
    ('状态', '状態', 'Status'),
    ('读回', '読戻し', 'Rdback'),
    ('串口 OK', 'シリアルOK', 'Serial'),
    ('启动中（30 s）', '起動中（30 s）', 'Booting (30 s)'),
    ('等 30 s（不发任何帧）', '30 s 待ち（フレーム送信なし）', 'Wait 30 s (no frames sent)'),
    ('保持正常（不报）', '正常のまま（報告しない）', 'Stays normal (no alarm)'),
    ('停止轮询', 'ポーリング停止', 'Polling stopped'),
    ('启动中', '起動中', 'Booting'),
    ('轮询中', 'ポーリング中', 'Polling'),
    ('停（装置结束）', '停止（装置終了）', 'Stopped (equipment end)'),
    ('等 30 s', '30 s 待ち', 'Wait 30 s'),
    ('开', '開', 'Open'),
    ('① ON', '① ON', '① ON'),
    ('③ OFF', '③ OFF', '③ OFF'),
    ('② 50.0', '② 50.0', '② 50.0'),
    ('① 25.0', '① 25.0', '① 25.0'),
    ('③ ON', '③ ON', '③ ON'),
    ('② OFF', '② OFF', '② OFF'),
    ('ACK ×3', 'ACK ×3', 'ACK ×3'),
    ('ACK ×2', 'ACK ×2', 'ACK ×2'),
    ('一致', '一致', 'Match'),
    ('运转中', '運転中', 'Running'),
    ('通水 · 50.0 · 运转', '通水・50.0・運転', 'Flow·50.0·Run'),
    ('25.0 · 停运转 · 停水', '25.0・停止・止水', '25.0·Stop·No flow'),
    ('安定 = 0', '安定 = 0', 'Stable = 0'),
    ('安定 = 1', '安定 = 1', 'Stable = 1'),
    ('报警 bit', 'アラーム bit', 'Alarm bits'),
    ('25.0 · 停', '25.0・停止', '25.0·Stop'),
    ('蜂鸣', 'ブザー', 'Buzzer'),
    ('错误 · 蜂鸣', 'エラー・ブザー', 'Error·Buzzer'),
    ('补读', '再読出', 'Re-read'),
    ('读详细', '詳細読出', 'Detail'),
    ('正常', '正常', 'OK'),
    ('停止错误', '停止エラー', 'Stop err'),
    ('报警编号', 'AL番号', 'Alarm #'),
    ('应答 ×3', '応答 ×3', 'Reply ×3'),
    ('已消除 · 锁存', '解消済・ラッチ中', 'Cleared · latched'),
    ('通信异常 bit', '通信異常 bit', 'Comm error bit'),
    ('切断', '遮断', 'Cut off'),
    ('投入', '投入', 'Turn on'),
    ('重发', '再送', 'Retry'),
    ('无', '無', 'none'),
    ('继续运转', '運転継続', 'Keeps running'),
    ('1', '1', '1'),
    ('2', '2', '2'),
    ('3', '3', '3'),
    ('异常（锁存）', '異常（ラッチ）', 'Error (latched)'),
    ('报警（只显示）', 'アラーム（表示のみ）', 'Alarm (display only)'),
    ('停运转 · 停水', '運転停止・止水', 'Run off·No flow'),
    ('报警（接点断开）', 'アラーム（接点開）', 'Alarm (contact open)'),
    ('停止 ×3', '停止 ×3', 'Stop ×3'),
    ('继续运转（停不下来）', '運転継続（止められない）', "Keeps running (can't stop)"),
    ('运行', 'RUN', 'RUN'),
    ('停止 / 断电', 'STOP / 電源断', 'STOP / power off'),

    # ---------- 注记 ----------
    # 1-1
    ('清洗机初始化写温度 3 次没应答就报「通信初始化异常」，画面解除后重新写【推】。'
     'PLC 用自带的 Modbus 从站功能，收到写就回应答、值进缓存，不管温水器起没起来；等温水器起来再转发【P】。',
     '洗浄機は初期化の温度書込に 3 回応答がなければ「通信初期化異常」を出し、画面解除後に書き直す【推】。'
     'PLC は内蔵の Modbus スレーブ機能を使うので、書込を受けたら即応答して値をキャッシュに入れる。温水器が起動しているかどうかは関係なく、'
     '温水器が起動してから転送する【P】。',
     'If the cleaner\'s init temp write gets no reply 3 times, it raises "comm init error" and writes again after a reset on '
     'the screen [I]. The PLC uses its built-in Modbus slave: it replies to every write at once and keeps the value in cache, '
     'whether or not the heater is up, and forwards it once the heater is up [P].'),
    ('温水器「上电 30 s 以后才能开始通信」【推】。远程电源投入 / 切断是清洗机进 PLC、'
     'PLC 再输出给温水器【IO】，所以 PLC 从转发投入那一刻开始计 30 s，这段时间不发任何帧【P】。'
     '（之前定的是拿通水 ON 当起点；两个信号同时 ON【定】，换成远程电源本身更直接，结果一样。）',
     '温水器は「通電 30 s 後から通信可能」【推】。リモート電源の投入 / 遮断は洗浄機から PLC に入り、'
     'PLC が温水器へ出力する【IO】。そのため PLC は投入を転送した瞬間から 30 s を計り、その間フレームは一切送らない【P】。'
     '（以前は通水 ON を起点にしていた。両信号は同時に ON する【定】ので、リモート電源そのものを起点にした方が直接的で、結果は同じ。）',
     'The heater accepts communication only 30 s after power-on [I]. Remote power ON / OFF '
     'goes from the cleaner into the PLC, and the PLC outputs it to the heater [IO]; so the PLC starts the 30 s timer when it '
     'forwards power ON and sends no frames during that time [P]. (The start point used to be flow ON; both signals turn ON '
     'together [OK], so using remote power itself is more direct, with the same result.)'),
    ('等的这段时间清洗机已经在读报警，PLC 回全 0（当作正常）。满 30 s 后读 3 次都没应答，才按通信异常处理（锁存，要复位）【P】。',
     '待っている間も洗浄機はアラームを読みに来るので、PLC は全 0（正常扱い）を返す。30 s 経過後に 3 回読んで全部無応答なら、'
     '初めて通信異常として扱う（ラッチ、要リセット）【P】。',
     'While waiting, the cleaner is already reading alarms; the PLC answers all 0 (treated as normal). Only after 30 s, if '
     '3 reads all get no reply, is it handled as a comm error (latched, needs reset) [P].'),
    ('第一次状态应答里检查是不是串口模式（温水器面板可切本地 / 远程 / 串口）【推】，不是就报重故障【P，已定】。',
     '初回の状態応答でシリアルモードか確認する（温水器パネルでローカル / リモート / シリアルを切替可能）【推】。'
     'シリアルでなければ重故障【P・決定済】。',
     'The first status reply is checked for serial mode (the heater panel can switch local / remote / serial) [I]; '
     'if not serial → major fault [P, decided].'),
    ('ACK 只表示收到，执行结果要用确认命令读回核对【推】。通水 IO 一 ON，PLC 先不转发通水，等运转 ON 再发（见 2-1）。',
     'ACK は「受信した」という意味だけで、実行結果は確認コマンドで読み戻して照合する【推】。通水 IO が ON になっても '
     'PLC はまだ通水を転送せず、運転 ON を待って送る（2-1 参照）。',
     'ACK only means "received"; the result has to be read back with a confirm command [I]. When the flow IO turns ON, '
     'the PLC does not forward flow yet; it sends it with run ON (see 2-1).'),
    ('重故障 / 轻故障 DO 是 b 接点：PLC 程序跑起来就输出「正常」（接点闭合）。PLC 比清洗机晚起来的话，清洗机一开机就会看到故障，要确认上电顺序。',
     '重故障 / 軽故障 DO は b接点：PLC プログラムが動けば「正常」（接点閉）を出力する。PLC が洗浄機より遅く起動すると、'
     '洗浄機は電源投入直後に故障を見てしまうので、電源投入の順序を確認すること。',
     'Major / minor fault DOs are NC (b) contacts: once the PLC program runs, it outputs "normal" (contact closed). If the PLC '
     'boots later than the cleaner, the cleaner sees a fault right at power-up, so the power-up order must be checked.'),
    # 1-2
    ('远程电源切断经过 PLC【IO】，PLC 转发的同时停轮询、不判通信异常【P，已定】。通水和它同时 OFF【定】。',
     'リモート電源遮断は PLC を経由する【IO】。PLC は転送と同時にポーリングを止め、通信異常と判定しない【P・決定済】。'
     '通水も同時に OFF【定】。',
     'Remote power OFF passes through the PLC [IO]; while forwarding it, the PLC stops polling and does not flag a comm '
     'error [P, decided]. Flow turns OFF at the same time [OK].'),
    ('下次远程电源投入从头按 1-1 走：等 30 s 再开始通信。',
     '次のリモート電源投入からは 1-1 と同じ流れ：30 s 待ってから通信を開始する。',
     'From the next remote power ON, it follows 1-1 again: wait 30 s, then start communicating.'),
    ('投入期间断线照常判通信异常（见 4-2）。',
     '投入中の断線は通常どおり通信異常と判定する（4-2 参照）。',
     'A link loss while powered is still flagged as a comm error (see 4-2).'),
    # 2-1
    ('往温水器的顺序：开始 = 通水 ON → 温度 50.0 → 运转 ON；停止 = 温度 25.0 → 运转 OFF → 通水 OFF【定】。',
     '温水器への順序：開始 = 通水 ON → 温度 50.0 → 運転 ON、停止 = 温度 25.0 → 運転 OFF → 通水 OFF【定】。',
     'Order to the heater: start = flow ON → temp 50.0 → run ON; stop = temp 25.0 → run OFF → flow OFF [OK].'),
    ('PLC 等运转 ON 才发通水：温水器「通水 ON + 运转 OFF」会开入口阀流常温水【定】；运转中、停止中通水 OFF 都无效，停止中运转 OFF 无效【推】。',
     'PLC は運転 ON を待ってから通水を送る：温水器は「通水 ON + 運転 OFF」で入口弁を開けて常温水を流すため【定】。'
     '運転中・停止中の通水 OFF はどちらも無効、停止中の運転 OFF も無効【推】。',
     'The PLC sends flow only together with run ON: with "flow ON + run OFF" the heater opens its inlet valve and passes '
     'room-temperature water [OK]. Flow OFF is ignored while running or stopping, and run OFF is ignored while stopping [I].'),
    ('ACK 只表示收到【推】。发完 3 帧马上读回目标温度和状态核对；不一致就重发，3 次还不对按通信异常处理（重故障）【P，暂定】。',
     'ACK は受信しただけ【推】。3 フレーム送信後すぐ目標温度と状態を読み戻して照合し、不一致なら再送、3 回合わなければ'
     '通信異常（重故障）として扱う【P・暫定】。',
     'ACK only means received [I]. Right after the 3 frames the PLC reads back the target temp and status; on a mismatch it '
     'resends, and after 3 mismatches it is a comm error (major fault) [P, tentative].'),
    ('PLC 用自带的 Modbus 从站功能，清洗机的写马上就有应答（不等温水器）；程序看到值变了再发 3 帧（合计约 0.2～0.3 s）【P】。'
     '所以清洗机拿到应答不代表温水器收到了，转发失败按通信异常报重故障（见 4-2）。图上请求和应答画在同一时刻。',
     'PLC は内蔵の Modbus スレーブ機能を使うので、洗浄機の書込にはすぐ応答する（温水器を待たない）。プログラムが値の変化を見てから '
     '3 フレームを送る（合計約 0.2～0.3 s）【P】。つまり洗浄機が応答を受けても温水器が受信したとは限らず、転送失敗は通信異常として'
     '重故障を出す（4-2 参照）。図では要求と応答を同じ時刻に描いている。',
     "The PLC uses its built-in Modbus slave, so the cleaner's write is answered at once (without waiting for the heater); "
     'the program sees the value change and then sends the 3 frames (about 0.2–0.3 s in total) [P]. So a reply to the '
     'cleaner does not mean the heater got it; a failed forward raises a major fault as a comm error (see 4-2). '
     'Requests and replies are drawn at the same moment.'),
    ('手动模式下清洗机投入开始就开投入阀，不等安定【推】。',
     '手動モードでは洗浄機は投入開始で投入弁を開け、安定を待たない【推】。',
     'In manual mode the cleaner opens the supply valve at supply start without waiting for stable [I].'),
    ('安定 DO 跟着状态更新：ON 最多晚 3 s（等下一次状态读出）；停的时候发完 3 帧马上读回，OFF 跟着读回走【P】。'
     '读回 = 目标温度 + 装置状态两帧，图上合成一格。运转 OFF 后安定位清零这一点待确认。',
     '安定 DO は状態の更新に従う：ON は最大 3 s 遅れる（次の状態読出を待つ）。停止時は 3 フレーム送信後すぐ読み戻し、'
     'OFF は読み戻しに従う【P】。読み戻し = 目標温度 + 装置状態の 2 フレームで、図では 1 マスにまとめている。'
     '運転 OFF 後に安定 bit がクリアされる点は要確認。',
     'The stable DO follows status updates: ON is up to 3 s late (it waits for the next status read); when stopping, the '
     'readback right after the 3 frames turns it OFF [P]. Readback = target temp + equipment status (2 frames), drawn as '
     'one cell. That the stable bit clears after run OFF is TBC.'),
    # 2-2
    ('自动模式下清洗机等安定 ON 才进投入开始【定】，所以安定 DO 晚到会直接拖慢投入。读出周期已定 3 s，最多晚 3 s。',
     '自動モードでは洗浄機は安定 ON を待って投入開始に進む【定】ので、安定 DO が遅れるとそのまま投入が遅れる。'
     '読出周期は 3 s に決定済で、遅れは最大 3 s。',
     'In auto mode the cleaner waits for stable ON before supply start [OK], so a late stable DO directly delays the supply. '
     'The read cycle is fixed at 3 s, so it is at most 3 s late.'),
    ('往温水器发的内容和手动（2-1）一样，只是触发时机不同；发完同样读回核对。',
     '温水器に送る内容は手動（2-1）と同じで、トリガのタイミングが違うだけ。送信後も同じく読み戻して照合する。',
     'What is sent to the heater is the same as manual (2-1); only the trigger timing differs. It is read back the same way.'),
    ('阀的延时参数（准备开始 → 运转 ON、投入开始 → 排水阀关、投入停止 → 投入阀关）图上省略了【推】。',
     '弁の遅延パラメータ（準備開始 → 運転 ON、投入開始 → 排水弁閉、投入停止 → 投入弁閉）は図では省略【推】。',
     'Valve delay parameters (prep start → run ON, supply start → drain valve close, supply stop → supply valve close) '
     'are left out of the chart [I].'),
    # 3-1
    ('清洗机 500 ms 读一次，PLC 3 s 读一次温水器。清洗机的读由 PLC 直接用缓存回答，不等温水器【P】。',
     '洗浄機は 500 ms ごと、PLC は 3 s ごとに温水器を読む。洗浄機の読出には PLC がキャッシュで直接応答し、温水器を待たない【P】。',
     "The cleaner reads every 500 ms; the PLC reads the heater every 3 s. The PLC answers the cleaner's reads from cache "
     'without waiting for the heater [P].'),
    ('温水器状态变了以后，DO 和读应答最多晚 3 s 才跟上（这张图里 1.25 s 变安定，3.0 s 才反映出来）。'
     '请求和应答画在同一时刻：正常时一问一答只要几十 ms。',
     '温水器の状態が変わってから、DO と読出応答が追従するまで最大 3 s 遅れる（この図では 1.25 s で安定になり、3.0 s でようやく反映）。'
     '要求と応答は同じ時刻に描いている：正常時の 1 往復は数十 ms。',
     'After the heater status changes, the DO and read replies catch up at most 3 s later (here it becomes stable at 1.25 s '
     'and shows up only at 3.0 s). Requests and replies are drawn at the same moment: a normal round trip takes tens of ms.'),
    ('平时只读装置状态（运转、入口阀、停止 / 继续错误、加热、通水、安定、串口模式、漏液），应答十几个字节【推】。'
     '状态里的错误位亮了才读报警详细（应答 130 多字节，9600 bps 下约 0.15 s），见 4-1【P】。',
     '普段は装置状態（運転・入口弁・停止 / 継続エラー・加熱・通水・安定・シリアルモード・漏液）だけを読み、応答は十数バイト【推】。'
     '状態のエラー bit が立った時だけアラーム詳細を読む（応答 130 バイト超、9600 bps で約 0.15 s）。4-1 参照【P】。',
     'Normally only the equipment status is read (run, inlet valve, stop / continue error, heating, flow, stable, serial mode, '
     'leak); the reply is a dozen-odd bytes [I]. Alarm detail is read only when a status error bit is set (reply 130+ bytes, '
     'about 0.15 s at 9600 bps), see 4-1 [P].'),
    ('报警不画在这张图里，见 4。',
     'アラームはこの図には描かない。4 を参照。',
     'Alarms are not drawn in this chart; see 4.'),
    # 4-1
    ('复位 ON 约 5 s，OFF 那一刻清洗机检查重故障输入和报警 bit 是否正常，正常才解除【推】。'
     '所以 PLC 在复位上升沿就要：发复位给温水器 → 马上补一次状态读出 → 在 OFF 之前把 DO 和 bit 清掉【P】。',
     'リセットは約 5 s ON で、OFF の瞬間に洗浄機が重故障入力とアラーム bit が正常かを確認し、正常なら解除【推】。'
     'そのため PLC はリセットの立ち上がりで：温水器にリセットを送る → すぐ状態を 1 回追加読出 → OFF までに DO と bit を'
     'クリアする必要がある【P】。',
     'Reset is ON for about 5 s; at the moment it turns OFF the cleaner checks that the major fault input and the alarm bits '
     'are normal, and clears only if they are [I]. So on the reset rising edge the PLC must: send reset to the heater → do '
     'one extra status read right away → clear the DO and bits before OFF [P].'),
    ('原因没消除就复位：温水器还在报警，DO 不清，OFF 时检查不过 → 解除失败【推】。',
     '原因が解消していないのにリセット：温水器はアラームのまま、DO はクリアされず、OFF 時のチェックで NG → 解除失敗【推】。',
     'Reset before the cause is removed: the heater still alarms, the DO is not cleared, the check at OFF fails → '
     'not cleared [I].'),
    ('轻故障时序一样：状态里「继续错误」位 → 轻故障 DO【推】，温水器继续加热、清洗机不停，复位一样走【推】。',
     '軽故障もタイミングは同じ：状態の「継続エラー」bit → 軽故障 DO【推】。温水器は加熱を続け、洗浄機も止まらない。'
     'リセットも同じ流れ【推】。',
     'A minor fault has the same timing: status "continue error" bit → minor fault DO [I]; the heater keeps heating, the '
     'cleaner does not stop, and reset works the same way [I].'),
    ('报警详细：温水器的报警编号和清洗机读的报警 bit 是同一套编号，PLC 按编号直接换算，不用逐条对照【推】。'
     '读详细的应答比较长（约 0.15 s），所以只在错误位亮了才读【P】。',
     'アラーム詳細：温水器のアラーム番号と洗浄機が読むアラーム bit は同じ番号体系なので、PLC は番号で直接変換し、'
     '1 件ずつの対照表は要らない【推】。詳細読出の応答は長い（約 0.15 s）ので、エラー bit が立った時だけ読む【P】。',
     "Alarm detail: the heater's alarm numbers and the alarm bits the cleaner reads use the same numbering, so the PLC "
     'maps them directly by number, with no item-by-item table [I]. The detail reply is long (about 0.15 s), so it is '
     'read only when an error bit is set [P].'),
    ('清洗机有复位和蜂鸣器复位两个 IO【IO】。蜂鸣器复位 → 发蜂鸣器复位；复位 → 发错误复位 + 蜂鸣器复位（之前定的做法保留）【P】。',
     '洗浄機にはリセットとブザーリセットの 2 つの IO がある【IO】。ブザーリセット → ブザーリセットを送信、'
     'リセット → エラーリセット + ブザーリセットを送信（以前決めたやり方を維持）【P】。',
     'The cleaner has two IOs: reset and buzzer reset [IO]. Buzzer reset → send buzzer reset; reset → send error reset + '
     'buzzer reset (the earlier decision is kept) [P].'),
    ('清洗机收到重故障后关运转 / 通水、写 25.0：还没定。',
     '重故障を受けた洗浄機が運転 / 通水を切り 25.0 を書く件：まだ未定。',
     'The cleaner turning off run / flow and writing 25.0 after a major fault: not decided yet.'),
    ('报警中温水器已经自己停了，转发停止 3 帧可能回「现在不能执行」的 NAK【推】。这种 NAK 不算通信失败，'
     '以读回结果为准；「数据异常」的 NAK 才算【P】。',
     'アラーム中は温水器が既に自ら停止しているので、停止 3 フレームの転送に「現在実行不可」の NAK が返る可能性がある【推】。'
     'この NAK は通信失敗に数えず、読み戻し結果で判断する。「データ異常」の NAK だけを数える【P】。',
     'During an alarm the heater has already stopped by itself, so the forwarded 3 stop frames may get a "cannot execute now" '
     'NAK [I]. That NAK does not count as a comm failure; the readback decides. Only a "data error" NAK counts [P].'),
    ('漏液类报警也一样：PLC 不自己关运转和通水，等清洗机看到重故障后自己停（已定）。也可以让温水器侧自己关，这里不采用。',
     '漏液系アラームも同じ：PLC は自分で運転と通水を切らず、洗浄機が重故障を見て自ら止めるのを待つ（決定済）。'
     '温水器側で自ら切る方法もあるが、ここでは採用しない。',
     'Leak alarms work the same way: the PLC does not turn off run and flow itself; it waits for the cleaner to stop on '
     'seeing the major fault (decided). Letting the heater side shut off by itself is also possible, but not used here.'),
    # 4-2
    ('超时 1000 ms、重试 3 次按常见的串口设定【推】【P】。'
     '没应答的请求：斜线格「无」紧跟在请求后面，表示等到超时；失败次数和判断画在同一时刻。',
     'タイムアウト 1000 ms・リトライ 3 回は一般的なシリアル通信の設定【推】【P】。'
     '応答のない要求は、直後の「無」枠でタイムアウトまで待ったことを表し、失敗回数と判定は同じ時刻に描いている。',
     'Timeout 1000 ms and 3 retries are common serial settings [I][P]. A request with no '
     'reply is followed directly by a "none" box, meaning it waited until the timeout; the fail count and the decision are '
     'drawn at that same moment.'),
    ('温水器没有通信看门狗，断线后串口停不下它【推】。远程电源经过 PLC【IO】，'
     '所以 PLC 判通信异常的同时自己输出一次远程电源切断，温水器断电停下【P，已定】。',
     '温水器には通信ウォッチドッグがなく、断線後はシリアルでは止められない【推】。リモート電源は PLC を経由する【IO】ので、'
     'PLC は通信異常と判定すると同時に自らリモート電源遮断を 1 回出力し、温水器は電源断で止まる【P・決定済】。',
     'The heater has no comm watchdog, so after a link loss serial cannot stop it [I]. Remote power passes through the '
     'PLC [IO], so when the PLC flags a comm error it also outputs one remote power OFF by itself, and the heater stops '
     'by losing power [P, decided].'),
    ('切断以后温水器一直断电，PLC 停轮询；要等清洗机下次装置启动（远程电源投入）才重新上电，之后按 1-1 等 30 s【P】。',
     '遮断後、温水器は電源断のままで、PLC はポーリングを止める。洗浄機の次の装置起動（リモート電源投入）で再び通電し、'
     'その後は 1-1 どおり 30 s 待つ【P】。',
     "After the cut, the heater stays unpowered and the PLC stops polling; it is powered again only at the cleaner's next "
     'equipment start (remote power ON), then waits 30 s as in 1-1 [P].'),
    ('两边断线都要复位：通信恢复以后清洗机复位才清重故障 DO。温水器还没起来就复位：PLC 不清，OFF 时检查不过 → 解除失败【P】。',
     '両側の断線ともリセットが必要：通信が復旧した後に洗浄機がリセットして初めて重故障 DO をクリアする。'
     '温水器がまだ起動していないのにリセット：PLC はクリアせず、OFF 時のチェックで NG → 解除失敗【P】。',
     'A link loss on either side needs a reset: the major fault DO clears only when the cleaner resets after comm is back. '
     'Reset before the heater is up: the PLC does not clear it, the check at OFF fails → not cleared [P].'),
    ('「数据异常」的 NAK 连续 3 次、写完读回 3 次不一致也算通信异常，一样切电源，报警 bit 不一样；'
     '「现在不能执行」的 NAK 不算，以读回为准【P】。断线期间 PLC 照常回清洗机的 Modbus，不让清洗机报 485 异常【P】。',
     '「データ異常」の NAK が 3 回連続、書込後の読み戻しが 3 回不一致の場合も通信異常とし、同じく電源を遮断する（アラーム bit は別）。'
     '「現在実行不可」の NAK は数えず、読み戻しで判断【P】。断線中も PLC は洗浄機の Modbus に通常どおり応答し、'
     '洗浄機に 485 異常を出させない【P】。',
     '3 consecutive "data error" NAKs, or 3 readback mismatches after a write, also count as a comm error with the same power '
     'cut (different alarm bit); a "cannot execute now" NAK does not count, the readback decides [P]. During the link loss '
     "the PLC keeps answering the cleaner's Modbus, so the cleaner does not raise a 485 error [P]."),
    # 4-3
    ('清洗机读报警失败 3 次只报「报警读取异常」，只显示、不停机【推】。所以要靠 PLC 自己判断线、让温水器停【P】。'
     '斜线格「无」紧跟在请求后面，表示清洗机等到超时才读下一次。',
     '洗浄機はアラーム読出に 3 回失敗しても「アラーム読出異常」を出すだけで、表示のみ・停止しない【推】。'
     'そのため PLC 自身が断線を判定して温水器を止める必要がある【P】。要求直後の「無」枠は、洗浄機がタイムアウトまで待ってから'
     '次を読むことを表す。',
     'After 3 failed alarm reads the cleaner only shows "alarm read error": display only, no stop [I]. So the PLC itself '
     'must detect the link loss and stop the heater [P]. The "none" box right after a request means the cleaner waits '
     'until the timeout before the next read.'),
    ('PLC 判断线的时间：暂定 5 s（500 ms × 10），还没定。',
     'PLC が断線と判定するまでの時間：暫定 5 s（500 ms × 10）、未定。',
     'Time until the PLC declares a link loss: 5 s for now (500 ms × 10); not decided yet.'),
    ('断线期间清洗机要是写温度（投入开始 / 停止），会报「温度设定异常」→ 温水停止【推】。',
     '断線中に洗浄機が温度を書込むと（投入開始 / 停止）、「温度設定異常」→ 温水停止になる【推】。',
     'If the cleaner writes a temp during the link loss (supply start / stop), it raises "temp set error" → hot water stop [I].'),
    ('两边断线都要复位：线修好了也要复位才清重故障 DO【P】。清洗机自己的「报警读取异常」在画面上无条件解除【推】。',
     '両側の断線ともリセットが必要：線が直ってもリセットしないと重故障 DO はクリアされない【P】。'
     '洗浄機自身の「アラーム読出異常」は画面で無条件に解除できる【推】。',
     "A link loss on either side needs a reset: even after the line is fixed, the major fault DO clears only on reset [P]. "
     "The cleaner's own \"alarm read error\" is cleared on the screen unconditionally [I]."),
    # 4-4
    ('故障 DO 是 b 接点：PLC 断电或停止运行时接点断开，清洗机马上看到重故障和轻故障，不需要 PLC 做任何事。'
     '图里按逻辑画（红 = 报警）。',
     '故障 DO は b接点：PLC が電源断・停止すると接点が開き、洗浄機はすぐ重故障と軽故障を見る。PLC 側で何もする必要はない。'
     '図は論理で描いている（赤 = アラーム）。',
     'Fault DOs are NC (b) contacts: when the PLC loses power or stops, the contacts open and the cleaner sees major and '
     'minor fault at once, with nothing needed from the PLC. Drawn as logic (red = alarm).'),
    ('PLC 停了以后清洗机这边：读报警失败 3 次 →「报警读取异常」只显示；写温度失败 3 次 →「温度设定异常」→ 温水停止【推】。'
     '斜线格「无」紧跟在请求后面，表示等到超时。',
     'PLC 停止後の洗浄機側：アラーム読出失敗 3 回 →「アラーム読出異常」表示のみ、温度書込失敗 3 回 →「温度設定異常」→ '
     '温水停止【推】。要求直後の「無」枠はタイムアウトまで待つことを表す。',
     'On the cleaner side after the PLC stops: 3 failed alarm reads → "alarm read error", display only; 3 failed temp '
     'writes → "temp set error" → hot water stop [I]. The "none" box right after a request means waiting until the timeout.'),
    ('温水器没有通信看门狗，PLC 停了也按最后状态继续运转。远程电源投入 / 切断也要经过 PLC【IO】，'
     'PLC 停着时清洗机切电源也传不到温水器。没有急停，写进风险评估（已定，这一条要补进去）。',
     '温水器には通信ウォッチドッグがなく、PLC が止まっても最後の状態のまま運転を続ける。リモート電源の投入 / 遮断も PLC を'
     '経由する【IO】ので、PLC 停止中は洗浄機が電源を切っても温水器に届かない。非常停止はなく、リスクアセスメントに記載する'
     '（決定済、この項目は追記が必要）。',
     "The heater has no comm watchdog, so it keeps running in its last state even if the PLC stops. Remote power ON / OFF "
     "also goes through the PLC [IO], so while the PLC is stopped the cleaner's power cut does not reach the heater. "
     'There is no E-stop; this goes into the risk assessment (decided; the item still has to be added).'),
    ('PLC 重启时远程电源早就投入了：温水器已经上电，不用再等 30 s，直接读【P】。'
     'PLC 重新运行后：先读一次温水器状态，按清洗机当前的运转 / 通水补发停止；故障 DO 保持报警，'
     '清洗机读报警也回「报警」，等清洗机复位才解除（PLC 自己断也算断线，一样要复位）【P】。',
     'PLC 再起動時にはリモート電源は既に投入済：温水器は通電しているので 30 s 待たずにすぐ読む【P】。'
     'PLC 運転再開後：まず温水器の状態を 1 回読み、洗浄機の現在の運転 / 通水に合わせて停止を再送する。故障 DO はアラームのまま保持し、'
     '洗浄機のアラーム読出にも「アラーム」を返し、洗浄機のリセットで解除する（PLC 自身の停止も断線扱いで、同じくリセットが必要）【P】。',
     'When the PLC restarts, remote power is already ON: the heater is powered, so the PLC reads right away without waiting '
     '30 s [P]. After the PLC runs again: it reads the heater status once and resends stop according to the cleaner\'s '
     'current run / flow; the fault DOs stay in alarm, the cleaner\'s alarm reads also get "alarm", and it clears on the '
     'cleaner\'s reset (a PLC stop also counts as a link loss and needs a reset too) [P].'),
]

LANGS = ('ja', 'en')
TR = {zh: dict(ja=ja, en=en) for zh, ja, en in ENTRIES}


def translator(lang):
    """返回 (t, missing)。t(s) 查不到时返回原文并记进 missing"""
    missing = []

    def t(s):
        if lang == 'zh' or not s:
            return s
        hit = TR.get(s)
        if hit is None:
            if s not in missing:
                missing.append(s)
            return s
        return hit[lang]
    return t, missing
