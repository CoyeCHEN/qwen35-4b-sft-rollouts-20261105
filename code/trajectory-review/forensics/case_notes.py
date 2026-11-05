"""Human-reviewed findings; analysis only, never used to change a native score."""
NOTES = {}

def add(key, finding, chain, limit, falsification, tools=()):
    NOTES[key] = dict(finding=finding, chain=chain, attribution_limit=limit,
                      falsification_test=falsification, key_tools=list(tools))

add('56a53f1e', '旧 M0 的 1 分存在可确认的陈旧二进制假阳性，不能证明完成了单文件 polyglot。', [
    'CONFIRMED：T149 分别编译 main.rs 和 cmain.cpp，留下 main、cmain 两个可执行文件；T151 的目录列表再次证明其存在。',
    'CONFIRMED：T152 写入 README，明确承认 “This is NOT a true polyglot file”；最后提交也是两个文件方案。',
    'CONFIRMED：官方 Verifier 对 main.rs 调用 g++ 已报编译错误，但未检查编译返回值，也未删除旧 cmain，随后运行 cmain 并通过测试。',
    'CONFIRMED：原始 reward=1 保持不变；有问题的是它对题意完成度的证明力。'],
    '没有修改官方测试或历史分数。这里是由代码、既有二进制和原始评分日志共同支持的评分漏洞路径，不是猜测新模型退化。',
    '仅在独立诊断副本中删除旧 main/cmain，再用冻结源码执行相同编译与测试；若仍能生成两个合格可执行文件，则反驳陈旧二进制解释。当前未运行该诊断。', [136, 149, 151, 152, 153, 154])
add('93e70998', '新 M0 未产出可执行的 Rust/C++ polyglot；自测命令掩盖了编译失败，最后仍 finish。', [
    'CONFIRMED：T2 首次 rustc 就因 #include 处语法错误失败，随后有多轮源码修改。',
    'CONFIRMED：T185、T187、T193、T195、T197 使用编译器输出管道及 echo，编译错误仍可得到 shell exit 0；这不是 Harness 伪造编译成功。',
    'CONFIRMED：T193 的原始 SSE 已包含 rm -f main cmain 和 head 管道，客户端拼接、Tool Start 与之相同。',
    'CONFIRMED：T198 最后写入源码后只查看头部，未成功编译；T200 finish，Verifier 因 /app/polyglot/main 不存在失败。',
    'CONFIRMED：旧 M0 保留二进制，新 M0 删除二进制后编译失败，因此这对 1→0 不是干净的能力退化对照。'],
    '任务 checksum 相同，但旧/新 Wheel、工具、Finish、显式采样字段和研究时限不同；未证明两个请求 Token、随机状态、实际权重文件逐字节相同。SSE 之前的生成 Token 未取到。',
    '独立复放最后源码，用无管道的编译命令逐项记录返回码和产物；再对同一冻结请求比较预 Parser 文本与 SSE。若源码能编译或 SSE 与生成文本不同，分别推翻产物/模型侧解释。', [2, 185, 187, 191, 193, 195, 197, 198, 199, 200])
add('2744cf85', '旧 M0 完成 C 扩展，原始官方评分通过；其源码与新 M0 并不相同。', [
    'CONFIRMED：T12/T14 分别写入 C 实现和 Python wrapper，T13 构建。',
    'CONFIRMED：T15 自测约 1.3×；T17 再测约 1.3–1.4×；官方六个 pytest item 全通过。',
    'CONFIRMED：T16 的额外检查脚本自身发生解包错误，不代表已完成的 C 扩展计算失败。'],
    '不能用一次旧测速证明新运行的 CPU 条件相同，也不能把两个不同实现当成同一产物重测。',
    '对旧、新最终产物在同一独立容器和固定输入矩阵中交错重复测速；若两者均稳定通过，优先调查原 Verifier 的运行差异。', [12, 13, 14, 15, 16, 17])
add('5ee06990', '新 M0 数值计算通过，但官方 N=5000、6000 性能断言失败；不是完全没解出来。', [
    'CONFIRMED：早期 C 编译错误和 wrapper NameError 后续都得到修正，不能将第一个错误当作终局原因。',
    'CONFIRMED：T33 和 T39 的公开 benchmark 报 5000≈1.5×、8000≈1.6×；T34/T35 的额外数值测试也通过。',
    'CONFIRMED：官方六个 pytest item 中四个通过，两个性能 item 分别约 1.12733× 和 1.16099×，低于 1.2×。',
    'CONFIRMED：公开 benchmark 未覆盖 N=6000；CTRF 按参数化测试名称合并为四行，不能把四行误报成实际只执行四个 item。'],
    '自测与 Verifier 的计时落差已确认；硬件争用、缓存、输入数据、wrapper 转换成本各占多少尚未确定。当前证据不支持直接说是 OOM、基础设施评分故障或 SFT 退化。',
    '保持最终源码及官方性能条件不变，在独立诊断中固定数据/线程/资源，交错重复公开 benchmark 和官方计时；若固定条件仍只在官方路径失败，定位输入或测量差异。', [7, 13, 18, 24, 25, 27, 30, 31, 32, 33, 34, 35, 38, 39, 40])

# NEW-M2 E1
add('cb24b7b6', 'ARS 没有交付 ars.R，反复提交空 bash 参数，最终达到三小时 Agent 时限。', [
    'CONFIRMED：初期安装/环境探测之后，出现 183 次完全相同的 bash {}，T190 至 T451，均缺少 command。',
    'CONFIRMED：额外提取 T190 的原始 SSE，Serving 已返回 bash + {}；Harness 不是在 Tool Start 才丢掉 command。',
    'CONFIRMED：工具校验把 required-command 错误返回，后续仍重复；官方测试找不到 ars.R。'],
    '已确认空参数在 Serving SSE 就存在；历史预 Parser 生成 Token 未取得，不能将参数消失首先发生在模型还是 Serving 直接定案。',
    '针对首次空 bash 决策提取原始生成/SSE；合法原始 command 若在 SSE 丢失，推翻纯模型归因；原始也为空则支持错误恢复策略问题。', [190, 191, 451])
add('798e06a4', 'Cython 任务持续修依赖与编译，最终模型服务连接中断；官方产物测试也仍失败。', [
    'CONFIRMED：开始出现不正确的 NumPy 命令用法，后续大量依赖和编译操作。',
    'CONFIRMED：最后请求 RemoteProtocolError / server disconnected，重试耗尽；这不是模型主动完成。',
    'CONFIRMED：官方实际执行测试，包含 vispy 导入缺失及编译模块/导入相关失败。'],
    '断连前尚未完成，不等于已证明它即使不中断也会失败；依赖应由任务提供还是 Agent 安装需结合原环境合同判断。',
    '冻结中断前工作区，只做独立依赖/编译验证，再核对同时间 Serving 服务日志；若工作区已满足所有测试，则反驳“中断前产物仍不完整”。')
add('f6231353', 'Chess 只交付一个着法，随后单次 Thinking 用满 81920；没有通过 read 查看图片。', [
    'CONFIRMED：初期访问 im.info[pixelformat] 报 KeyError，后续图像统计脚本有重复语法错误。',
    'CONFIRMED：记录中无 read 图片调用，主要自行分析 PNG/像素；最终 move.txt 只有 e2e4，未满足两着法要求。',
    'CONFIRMED：最后 Agent 请求 output=reasoning=81920、stopReason=length。'],
    '未调用 read 图片是行为事实，不代表模型物理上完全无法读取图像；未取得该长输出的预 Parser Token，不能排除 Serving 解码异常。',
    '对相同棋图和历史，固定输入 Token，比较 M0 与该 Checkpoint 的原始下一动作及 Thinking 终止概率；若预 Parser 已正常结束而 Harness 仍显示 length，则转查 Serving。')
add('b78177d1', '视频着法提取停在依赖/脚本探测并出现 Thinking length；同时官方评分 bootstrap 失败。', [
    'CONFIRMED：首轮 shell 引号错误后，转向 Python/wheel 探测及 os.walk 辅助脚本，反复精确编辑未命中。',
    'CONFIRMED：最后 Agent Thinking 81920；独立摘要也曾 length，二者不能混算。',
    'CONFIRMED：Verifier 无 CTRF，releases.astral.sh 连接失败，随后 uvx not found；原始 reward=0 不能作为有效任务评分。'],
    '可分析已发生的动作问题；不能依据未启动的官方测试推断最终任务成功与否。',
    '只恢复原 Verifier 公共依赖链，在独立身份中对保留工作区评分；若评分可运行且产物通过，推翻“该工作区必定失败”。')
add('8abcb82b', 'HTML filter 写出了文件，但文件在运行时异常；随后 Thinking 用满输出上限，没有修复。', [
    'CONFIRMED：仅五次模型调用、四次工具调用，之后最后 Thinking 达 81920。',
    'CONFIRMED：官方运行 filter.py 第 266 行 list(soup.naming_whitelist)，得到 NoneType 不可迭代错误。'],
    '这是实际代码运行错误，不是缺少官方评分；为何生成无效 API 用法、为何无法结束 Thinking，尚不能仅凭本轨迹归因到训练或后端。',
    '同一错误 Observation 冻结后比较 Checkpoint 下一动作；若其能稳定给出修复而长输出只在一个后端出现，则反驳权重单独解释。')
add('7f7371b8', 'Windows 任务停在磁盘/QEMU 探测与有语法错误的辅助脚本，没有启动要求的 VNC。', [
    'CONFIRMED：读取二进制磁盘、探测缺失的 strace，签名扫描脚本重复把 while 写在不合法的单行位置。',
    'CONFIRMED：三小时结束时官方检查找不到 :5901。'],
    '工具报错不是全部同一根因；strace 不存在本身也不是该任务必须预装的证明。',
    '按首个关键安装/启动失败向后对照，核实 Agent 是否已得到完整错误；若 Observation 被截断丢掉恢复所需部分，则优先查工具预算。')
add('9ccf45fd', '调度任务没有产出可评分的计划，多轮辅助脚本语法错误后达到三小时。', [
    'CONFIRMED：早期 Python 变量 i 未定义，后续 heredoc 结束标记包含 ? 或代码围栏，出现七次相同错误命令。',
    'CONFIRMED：官方测试缺少计划文件；中间出现摘要 length，不能把摘要失败都归为主 Agent Thinking。'],
    '相同命令多次出现不自动等于环境没变化；这里的重复语法本身由工具日志证明，但首次模型/Parser 分歧仍需原始生成。',
    '对首个 heredoc 错误的 Serving SSE 与实际 bash command 逐字符比较；若一致，再测试错误后是否保留了完整 stderr。')
add('3d172a45', 'RStan 未安装、分析未交付，最后 Thinking 81920；早期把 shell 重定向放进 R 代码。', [
    'CONFIRMED：R 表达式中混入 2>&1 等 shell 语法，工具产生语法错误。',
    'CONFIRMED：最后长 Thinking 反复讨论 --no-cache-dir，官方 RStan 与分析脚本相关测试失败。'],
    '安装 RStan 属于题目要求，不能仅因最终缺包把它称作环境预检失败。',
    '在原任务要求下比较第一次 R 错误之后各 Checkpoint 的下一动作；若同一 Observation 能正确纠正，说明该失败并非不可用环境的必然结果。')
add('01b43bc0', 'MTEB 没有给出要求的模型 ID，而将一段结果来源说明写入 result.txt。', [
    'CONFIRMED：长时间检索本地包/榜单文件，os.walk 解包及 inline try 有重复脚本错误。',
    'CONFIRMED：官方测试实际读到 “scandinavia_mteb: results from mteb_rankings.csv”，不符合模型 ID 要求；三小时终止。'],
    '不能把检索失败直接称作目标网站不可用；需要区分本地搜索策略与实际网络响应。',
    '冻结最早已拿到榜单信息的历史，比较下一步是否能提取有效模型 ID；若正确 ID 从未可见，则应转查信息可达性。')
add('ae9dd309', 'Polyglot 同时存在退出 137、清理失败和 Verifier 未启动，不能算普通模型零分。', [
    'CONFIRMED：先前多次 C/Rust 编译失败，末轮 /tmp/min_test.sh 还有 shell 语法错误。',
    'CONFIRMED：Agent exit 137、无 run_end；lifecycle 记录 release_failed / cleanup_confirmed=false。',
    'CONFIRMED：Verifier 最后 uvx not found，官方测试未执行，原始 reward=0 保留但评分可信度为 UNKNOWN。'],
    '137 只说明收到 SIGKILL 类退出信号，未取得 kernel/cgroup 证据，不能宣称 OOM 或怪模型。',
    '查原容器 OOMKilled、memory.events、宿主退出日志及清理日志；若没有内存杀进程证据，否定 OOM 定案。')
add('33499c19', 'Regex 停在辅助脚本和长 Thinking；Verifier 下载失败，原始零分无有效测试支撑。', [
    'CONFIRMED：sanitize_dict 等辅助脚本三引号错误多次出现。',
    'CONFIRMED：主 Agent 81920 Thinking length；摘要请求另有 length。',
    'CONFIRMED：Verifier 的 UV release 下载连接失败，随后 uvx not found，未获得 CTRF。'],
    '不能将下载失败转换成正则能力零分；也不能用摘要 length 次数代替主 Agent 次数。',
    '对现有 regex 产物独立运行原官方测试，并在长 Thinking 的同输入跨后端核验是否确实无结束 Token。')
add('0f6c5278', 'SAM 在 Agent 安装 360 秒时限处失败，未产生任何模型决策。', [
    'CONFIRMED：AgentSetupTimeoutError；calls=0，tools=0，无官方 reward。'],
    '没有模型动作可分析；不能把它列入模型不读图片、不会分割或解题零分。',
    '核对实际安装命令的最后一步和离线缓存可读性；同镜像无模型安装 smoke 通过前，模型能力假设无法检验。')
add('c2780a13', 'SPARQL 文件存在但语法不合法；最后长 Thinking 没有修复查询。', [
    'CONFIRMED：前期 Python 缺失和 Perl 辅助解析错误，随后产生查询。',
    'CONFIRMED：官方 parser 在 char 610 / line17 找到意外 {，Expected SelectQuery；最后 Agent Thinking 81920。'],
    '有文件不代表查询有效；这里是实际解析失败，不是官方评分下载失败。',
    '在独立只读解析中定位冻结查询语法，再将该错误 Observation 提供给各 Checkpoint；若 Observation 在原历史未可见，优先查反馈链。')
add('345dda62', '视频处理没有交付 jump_analyzer.py，反复分析容器/MP4 辅助脚本直到三小时。', [
    'CONFIRMED：初期执行 toml --version；该命令不存在不等于 Python toml 模块必定缺失。',
    'CONFIRMED：MP4 二进制解析脚本有重复语法错误，官方测试最终缺少 jump_analyzer.py。'],
    '不能从 CLI 探测错误推断依赖安装坏；应以真实 import 与任务合同为准。',
    '从首次可用视频/工具响应处比较下一步实现行为；若所有必要数据不可读，反驳单纯策略失败归因。')

# NEW-M1 E5
add('63815a3d', 'ARS 三小时超时后，日志工件损坏又阻止了同步/脱敏与评分；轨迹不能称完整。', [
    'CONFIRMED：351 次调用、348 次工具，仍未完成任务；期间主要安装 R 及辅助脚本。',
    'CONFIRMED：两个 artifact 身份有三处坏引用，例如声明 510884 字节、实际 494950，SHA 不同。',
    'CONFIRMED：原始 Result 自身也记录 Cannot redact a corrupt rollout artifact；官方 reward 为空，不是本审阅器制造的报错。'],
    '损坏字段不用于重建教师/Agent 实际可见上下文；只能分析其余可验证片段。损坏发生在写入、同步还是脱敏尚未确定。',
    '逐层对照容器原 artifact、回收副本与脱敏前后 SHA；找到首次不一致层，才能归因写入/传输/日志处理。')
add('7cb7da88', 'Chess 未交付 move.txt，花费三小时自行解析图片和反复修脚本。', [
    'CONFIRMED：未出现 read 图片调用；read_classes.py 等脚本有五次同类语法错误。',
    'CONFIRMED：官方测试明确 move.txt 不存在。'],
    '不读取图片工具与任务失败相关，但并非已证明训练数据造成了这种策略；原始预 Parser 输出缺失。',
    '冻结首次图片探测后的历史，比较 M0/该 Checkpoint 下一工具选择；若同 Token 输入在另一后端能调用 read，则查后端。')
add('57ec1e1d', '视频着法任务退出 137，之前启动大量 ffmpeg 并行工作，最后缺少 solution.txt。', [
    'CONFIRMED：末段计划/启动约 30 个 ffmpeg 并发命令，之后 Agent 137、Recorder 无 run_end。',
    'CONFIRMED：官方文件检查失败。'],
    '资源峰值是合理假设，但没有 OOMKilled/cgroup 证据，不能确认 137 是内存溢出，也不能把基础设施中断当正常完成。',
    '核对原容器资源事件与并发子进程时间线；若 137 来自外部终止或生命周期清理，推翻 OOM 解释。')
add('2f9a4c6b', '仅两次工具后就陷入 81920 Token Thinking，没有写 filter.py；不需要长历史就能复现失控。', [
    'CONFIRMED：最后请求 input=3233、output=reasoning=81920。',
    'CONFIRMED：官方测试因 filter.py 不存在失败。'],
    '3233 输入明显不接近 262144 上限，反驳“全部循环都由长上下文 overflow 导致”；仍需预 Parser 输出排除解码层异常。',
    '以该短输入 Token 做 M0/M1 E3/E5、同后端的确定性或 logprob 对照；再以同权重跨后端，分别证伪权重与 Serving 假设。')
add('91fe5792', 'Windows 目标未启动，反复磁盘/串口分析和有错误的辅助代码后超时。', [
    'CONFIRMED：探测错误 nginx 路径，后续串口辅助 Python 使用 0600 等不合当前 Python3 的语法。',
    'CONFIRMED：部分管道/echo 掩盖命令失败；官方未发现 :5901。'],
    '不能仅凭很多工具退出 0 宣称其启动成功；必须看 VNC/QEMU 实际状态。',
    '对首次失败的 QEMU/串口动作比较真实 stderr 与下一请求可见 Observation；若关键错误被移除，优先查预算链。')
add('d50fe93c', '调度任务脚本错误后超时，官方评分又因 UV 下载失败没有开始。', [
    'CONFIRMED：对 JSONL 使用 json.load 得到 ExtraData；后续 bid 未定义的自测多次出现，部分被 head/echo 掩盖。',
    'CONFIRMED：Verifier curl 无法连接 astral.sh，uvx not found，无 CTRF；原始 reward=0 不作有效零分。'],
    '可以确认动作/脚本问题，但不能用未执行的官方断言判断其计划是否合格。',
    '只恢复原 Verifier bootstrap 后，独立审计既有计划与官方 cost；若通过则反驳产物失败猜测。')
add('4394d772', 'MCMC 仍在构建依赖时模型服务断连，之后官方测试显示 RStan/分析尚未完成。', [
    'CONFIRMED：RStan、RcppEigen 构建与调试持续进行；最终 RemoteProtocolError / incomplete chunked read。',
    'CONFIRMED：连接异常与其他服务中断时间接近；官方测试实际运行但 RStan 及分析未通过。'],
    '同时间断连支持共享基础设施事件，但不能据此确定是存储、SSH、服务进程还是网络；未正常完成的产物失败不等于纯模型能力失败。',
    '查该响应 ID 对应的 Serving 原始日志和主机事件；若服务完整生成但客户端漏读，推翻模型主动停止解释。')
add('dde38f55', 'MTEB 长时间检索和错误脚本，没有生成 result.txt。', [
    'CONFIRMED：inline Python 语法、socket.connect 参数等错误重复出现。',
    'CONFIRMED：达到三小时，官方两个测试因 result.txt 不存在失败。'],
    '反复网络探测不等于目标数据确实不可访问；脚本本身的错误需先排除。',
    '在最早获得公开榜单内容的决策点比较提取模型 ID 的下一动作；若从未拿到内容，则独立验证原 URL 可达性。')
add('c7dfa174', 'Polyglot 多次源码编译错误，最后长 Thinking 而未生成 Rust 可执行文件。', [
    'CONFIRMED：C/Rust 混合源码引号和注释错误，编译探测多次执行。',
    'CONFIRMED：最后 Thinking 81920，官方缺少 /app/polyglot/main。'],
    '相同编译命令之间有修改源码，不能把五次同命令自动叫作五次毫无进展重试。',
    '对每次编译前源码做 SHA/错误位置差分；若错误确实移动且趋于修复，反驳“所有重复都无进展”。')
add('e808c4a4', 'Regex 最终文件使用 Python 不接受的 ?<[ 扩展，长 Thinking 未完成修复。', [
    'CONFIRMED：曾用 Perl 检验目标 Python 正则，存在方言不一致。',
    'CONFIRMED：官方在 position71 / line3 报 unknown extension ?<[；最后 input45510、output81920。'],
    '该长输出并非因 input+output 超过 262144，不能用上下文长度超限直接解释。',
    '将同一最终正则在要求的 Python re 中解析，比较模型获得明确错误后的纠正动作；若原 Observation 与下一请求不一致，转查 Harness。')
add('1e33f403', 'SPARQL 未交付查询文件，反复辅助解析/依赖探测直至三小时。', [
    'CONFIRMED：Python 命令缺失后继续编写有语法错误的 Perl 脚本，部分 echo 管道掩盖退出。',
    'CONFIRMED：官方实际测试找不到 solution.sparql。'],
    '任务对解释器的原始承诺需独立核对，不能把每个缺命令都当预检失效。',
    '核实原镜像中的必要解释器与 Agent PATH；若任务承诺的解释器在原环境也缺失，则应归环境合同问题。')
add('7d98d711', 'Video 没交付脚本，且真实 import 已暴露题面承诺的 toml 模块不可用。', [
    'CONFIRMED：实际执行 import cv2,numpy,toml 得到 ModuleNotFoundError: toml；题面声明环境已提供相关包。',
    'CONFIRMED：其后辅助代码还有 target_height 未定义等错误，三小时后官方缺少 jump_analyzer.py。'],
    '依赖合同不一致和后续动作错误并存。尚未确认是原镜像缺包、安装换解释器、PATH 还是虚拟环境隔离导致。',
    '对照原镜像、Agent.setup 后、正式 bash 三阶段 sys.executable/sys.path 与 import；首次变化处可证伪镜像/安装/环境泄漏假设。')

# NEW-M2 E3
add('3f4bc9f1', 'ARS 未交付 R 版本 ars.R，转向 Python/scipy 与安装脚本后超时。', [
    'CONFIRMED：未找到 R，随后探索 Python/scipy 替代及含三引号错误的安装辅助脚本。',
    'CONFIRMED：官方要求的 ars.R 不存在，三小时结束。'],
    '替代方案是否可能满足题意应按原任务判断；不能因做了很多探测就称有有效任务进展。',
    '从首次获得明确 R 交付要求后的决策比较工具选择；若模型未见完整题面/摘要丢失 R 要求，则优先查上下文。')
add('c4897256', 'Chess 正常 finish 但写了错误答案：第二着沿用题面示例 h1h8。', [
    'CONFIRMED：无 read 图片工具调用，主要自行解析 PNG 密度与像素，出现 decode 等错误。',
    'CONFIRMED：最终 e2e4 h1h8，官方第二着不匹配；Agent 正常闭合，所以不是所有失败都由超时造成。'],
    '题面例子进入答案是可见行为；其根源是图像能力、工具选择还是模型策略尚需冻结上下文对照。',
    '用原图与相同模板测试读图后候选着法概率，再与仅文本历史比较；若正确读图时能答对，缩小到工具/多模态输入路径。')
add('1fca8264', '视频着法任务超时，Verifier 又因 APT/TLS/UV bootstrap 失败而未执行官方断言。', [
    'CONFIRMED：Agent 长时间在依赖/wheel/网络探测，未正常闭合。',
    'CONFIRMED：Verifier 日志含 Ubuntu TLS 证书失败、混合包依赖无法解决、curl/uvx not found；无 CTRF。'],
    'Verifier 看到的 APT 状态是否被 Agent 改动需逐条对照；此处只确认评分链未成功，不能未经对照归管理员或模型。',
    '对照任务原始 APT 源和 Agent 实际修改命令；若 Agent 引入不兼容发行版源，属于工作区破坏，反驳纯宿主网络解释。')
add('c592f34a', 'HTML filter 最终源码保留了字面量 shell 替换表达式，Python 无法解析。', [
    'CONFIRMED：T541/T558 用单引号 sed 替换，写入字面量 $(cat /tmp/fallback_block.txt)，未执行 shell 展开。',
    'CONFIRMED：T560 py_compile 明确在 /app/filter.py:259 报 SyntaxError，仍继续大量辅助验证直到超时。',
    'CONFIRMED：官方也因运行脚本失败，不能只称“任务复杂/超时”。'],
    '错误在工具实际执行的脚本中可定位；是否原始模型生成即如此仍需预 Parser 证据，现有 Tool Call 到 Tool Start 没有参数变化。',
    '复放该 sed 的纯字符串转换即可证伪 shell 展开假设；对照首次错误后下一请求是否包含该 SyntaxError，区分未反馈与未纠错。', [541, 558, 560])
add('4ffe3aaf', 'Windows 任务未启动目标 VNC，时间消耗在 QEMU 编译与磁盘/串口探测。', [
    'CONFIRMED：早期缺 curl，后续尝试 QEMU5.2 编译及磁盘检查。',
    'CONFIRMED：三小时后官方找不到 :5901，QEMU 状态相关断言也失败。'],
    '需要安装 QEMU 本身属于任务步骤，不能预先完成它以提高模型分数。',
    '定位第一个实际 QEMU 启动命令，比较返回错误是否完整可见；若启动命令从未生成，优先解释为策略没有进入交付阶段。')
add('6ac52b2b', '调度计划已产生但成本远超阈值：2.483×10¹²，大于 3×10¹¹。', [
    'CONFIRMED：官方实际读取计划并运行性能检查，不是缺文件。',
    'CONFIRMED：bucket1 cost=2483023679002；Agent 在改辅助代码/摘要期间达到三小时。'],
    '与 M2 E5 数值一样，不等于已证明计划字节相同或模型必定复制；需要源码/产物 SHA 对照。',
    '比较两个阶段的计划及生成器 SHA，独立重算 bucket 成本；若不同计划仍同值，调查是否都停留在相同基线方案。')
add('6590f80c', 'MCMC 在 Token counter 连接失败时就退出，实际模型生成请求没有发送。', [
    'CONFIRMED：input_token_count_failure，counter_unavailable，四次 ConnectError，generation_request_sent=false；calls=tools=0。',
    'CONFIRMED：之后 Verifier 虽写原始零分，但它看到的是未经模型修改的环境。'],
    '该条没有任何模型决策，不能作为模型能力零分，也不能据此评价 M2 E3 的 RStan 安装能力。',
    '核对 counter/service 实例及连接错误，恢复后仅做无生成健康检查；若历史存在真实调用证据，则可推翻“零生成”分类。')
add('7f7559b9', 'MTEB 在 Agent.setup 360 秒处超时，无模型与评分。', [
    'CONFIRMED：AgentSetupTimeoutError，calls=tools=0，reward 缺失。'],
    '无轨迹可用于模型策略分析，不用名字猜测是 MTEB 网站或模型失败。',
    '独立核验实际安装步骤与缓存，不调用模型；找到安装最后阻塞点。')
add('3654d15a', 'Polyglot 未编译成功，末次 Thinking 出现连续 78531 个字符 0 并耗尽 81920 Token。', [
    'CONFIRMED：之前有源码/编译错误，官方缺少 Rust 可执行文件。',
    'CONFIRMED：解析后的 Assistant Thinking 出现极长重复 0，最后 length。'],
    '确认输出退化，不等于确认是训练权重还是 Serving 融合算子/增量解码；没有对应原始生成 Token。',
    '只对该冻结输入做同权重跨后端原始 Token 对照；若只有 SGLang 坏而 Transformers 正常，推翻权重单独解释。')
add('a0dded9e', 'Regex 未写 regex.txt，停在辅助脚本和摘要阶段直至时限。', [
    'CONFIRMED：初期解释器/文件探测之后反复处理数据与辅助代码。',
    'CONFIRMED：官方实际检查 regex.txt 缺失；有一次摘要 length。'],
    '摘要 length 是辅助请求，不应误写成主 Agent 81920 Thinking。',
    '从首次已有日志样例和要求时比较下一动作；同时核对摘要是否保留 regex.txt 交付要求，证伪摘要丢任务假设。')
add('af8f6b38', 'SPARQL 还在辅助解析阶段就遭遇模型服务流中断，未交付查询。', [
    'CONFIRMED：Perl 辅助脚本错误后，最后请求 incomplete chunked read。',
    'CONFIRMED：官方检查 solution.sparql 不存在。'],
    '连接中断是工程终止，不能把其未完成产物当作正常结束后的纯模型零分。',
    '对照同响应 ID 的服务日志、SSE 尾部和客户端关闭时刻，区分服务先停与客户端先断。')
add('f1a492a0', 'Video 辅助 Python 文件混入了 shell 命令，随后超时；官方测试又未能启动。', [
    'CONFIRMED：Python 源码中出现 python3 /tmp/check_builtins_write.py 2>&1 | head 等 shell 行，语法错误多次出现。',
    'CONFIRMED：Verifier 下载 astral.sh 失败，uvx not found，无 CTRF；原始零分保持但有效评分为 UNKNOWN。'],
    '已确认辅助脚本/错误恢复问题；官方评分未运行，不能从 raw reward=0 推断最终视频算法能力。',
    '定位该文件首次写入及 SSE 参数，检查 Python/heredoc 边界；若原始生成正确而实际文件不同，转查工具执行链。')

# NEW-M2 E5
add('8a510b0c', 'ARS 第一次等待后台安装时 job_id 已少一个字符，之后绕开正确 Job 继续探测，最终无 ars.R。', [
    'CONFIRMED：T3 返回 32 字符 52b91d921dc442e4bd4fb2422209d0f4；T4 请求 31 字符 52b91d921dc442e4bd4fb242209d0f4。',
    'CONFIRMED：T4 对应的 Provider Payload 尾部仍包含正确的 32 字符 ID，未包含错误 ID；输入 usage 为 3915，并非长历史压缩后失去 ID。',
    'CONFIRMED：原始 Serving SSE 已携带错误的 31 字符 ID，Harness 解析与实际执行未改变；Unknown job_id 并不证明服务重启丢 Job。',
    'CONFIRMED：之后安装/辅助脚本继续但三小时后仍没有 ars.R。'],
    '已排除这一次错误由 Harness Tool Start 改写引入；未拿到 SGLang Parser 前文本，不能继续确定是模型抄错还是 Serving 改写。',
    '取得对应预 Parser 生成文本。若有正确 32 字符而 SSE 错，定位 Serving Parser；若原始就是 31 字符，支持参数复制/策略问题。', [3, 4, 5])
add('12bb124c', 'Chess 长时间自行解析 PNG，超时后 Verifier 下载失败，没有有效官方评分。', [
    'CONFIRMED：没有 read 图片工具调用，早期把 PIL Image 当可下标对象，后续继续像素/二进制分析。',
    'CONFIRMED：Verifier 的 releases.astral.sh 连接失败、uvx not found，无 CTRF。'],
    '不能把该原始零分与实际棋力失败直接画等号；已观察到的工具选择偏差另行保留。',
    '独立恢复官方评分后只评现有工作区，同时做固定图像输入下一动作对照；两类结果分别检验产物与策略。')
add('a6f3b858', '视频着法没有交付 solution.txt，三小时主要耗在安装和探测而非形成最终答案。', [
    'CONFIRMED：初期依赖不足，随后大量安装/查询；末段仍处在摘要/执行中。',
    'CONFIRMED：官方测试实际运行且 solution.txt 不存在。'],
    '需按原任务区分必须自装依赖和镜像承诺依赖，不能一概称预检失效。',
    '核实首个任务媒体资产可读与原镜像工具清单；若公开资产实际不可读，则否定完全由模型策略造成的解释。')
add('50f0ad68', 'Filter 已有脚本但 Agent 超时；官方 XSS 测试下载攻击向量时断连，评分被基础设施污染。', [
    'CONFIRMED：原测试 download_attack_vectors() → urllib.request.urlretrieve 在真正测试 XSS 前抛 RemoteDisconnected。',
    'CONFIRMED：另一个 clean-html 断言也失败，必须分别看；不能用第一个下载失败证明过滤算法不合格。'],
    '模型动作问题和评分下载问题并存；原始 reward=0 不足以给这次完整 XSS 能力定案。',
    '在官方资源身份相同且可达的独立评分中重测冻结脚本；若仍在算法断言失败则支持产物问题，若通过则主要是评分链。')
add('3e2ef496', 'Windows 任务在依赖/QEMU 准备期间模型服务断连，最终没有目标 VNC。', [
    'CONFIRMED：持续构建/探测，最终 Server disconnected without sending a response。',
    'CONFIRMED：官方网络/QEMU 检查失败，没有 :5901。'],
    '连接中断不是模型自主结束；不得用这次结束方式证明 M2 E5 在正常预算下也一定无法完成。',
    '对照同时间四个服务的响应与主机事件；若只有该请求断而服务正常，反驳整机故障解释。')
add('0aaba73e', '调度计划可读但不达成本要求，bucket1 约为阈值 8.28 倍。', [
    'CONFIRMED：官方读取计划，计算 cost=2483023679002 > 3e11，其他部分测试可执行。',
    'CONFIRMED：Agent 到三小时仍在辅助代码/改进阶段。'],
    '与 M2 E3 数值相同只证明这项代价相同，不证明权重或轨迹重复。',
    '比对两个最终计划/生成器 SHA 与首次改进决策，判断是否都未离开同一基线；若已产生不同有效改进，则反驳简单复制解释。')
add('b0daf50d', 'Polyglot 源码仍不能编译，三小时后缺少 Rust 主程序。', [
    'CONFIRMED：首批混合源文件两种编译均失败，后续继续注释/引号及工具探测。',
    'CONFIRMED：官方测试找不到 /app/polyglot/main；Agent 超时而非正常完成。'],
    '官方测试本身有忽略编译返回值的漏洞，但本次没有可复用二进制，所以并未因此获得假阳性。',
    '对最后源码以独立编译返回码检查，再定位首次错误后是否出现有方向的源码变化；区分有效迭代与无进展工具重复。')
add('ed6c9df3', 'Regex 有文件但括号不平衡，官方 parser 在 position183 拒绝。', [
    'CONFIRMED：Agent 反复辅助脚本、正则处理后达到三小时。',
    'CONFIRMED：官方对现有 regex.txt 运行 Python re，报 unbalanced parenthesis at position183。'],
    '这不是缺文件或 Verifier 无法启动；错误已落到最终产物。',
    '对照最终写入、最后一次本地解析、自测 stderr 与下一请求，找为何未纠正；若本地从未运行同方言 parser，支持验证策略问题。')
add('10eb84ca', 'SPARQL 的生成请求未发送，Token counter 不可达，原始零分不能评价模型。', [
    'CONFIRMED：counter_unavailable，四次 ConnectError，generation_request_sent=false，calls=tools=0。',
    'CONFIRMED：Verifier 随后发现初始工作区没有 solution.sparql。'],
    '零生成的任务文件缺失不能归因到 M2 E5 的决策能力。',
    '用历史真实请求账本反证是否曾有生成；没有则保留工程未执行分类，不作模型比较。')
add('3a830fe5', 'Video 辅助解析脚本错误并超时；Verifier 因 UV 下载失败没有执行评分。', [
    'CONFIRMED：把 VideoCapture 当可迭代对象，以及 MP4 递归函数参数数量错误，部分管道掩盖失败。',
    'CONFIRMED：Verifier curl 无法连接 astral.sh，uvx not found，无 CTRF。'],
    '错误动作可核验，但原始 reward=0 没有实际官方算法断言支持。',
    '独立恢复评分依赖后只测冻结工作区；同时在原始错误 Observation 上比较下一动作，不把两种实验混在一个分数里。')

for key, name in [('cd9e3b85', 'M2 E5 / Cython'), ('6779c19e', 'M2 E5 / MCMC'), ('d60e6bf7', 'M2 E3 / Cython')]:
    add(key, name + '：Token counter 不可达，未发送模型生成请求。', [
        'CONFIRMED：Recorder 的 input_token_count_failure 记录 counter_unavailable、generation_request_sent=false；calls=tools=0。',
        'CONFIRMED：原始 Result 的退出或后续 Verifier 结果单独保留，不将初始工作区评分当作模型解题成绩。'],
        '这里没有可分析的模型动作，不能用数据或训练质量解释该条。',
        '只核对该 Trial 的真实请求账本和服务连接事件；若发现相同身份存在成功生成请求，则重新检查零生成证据。')
for key, name in [('98cd0ac5', 'M2 E5 / MTEB'), ('2350788f', 'M2 E5 / SAM'), ('5e708f48', 'M2 E3 / SAM')]:
    add(key, name + '：Agent.setup 超时，尚未开始模型执行。', [
        'CONFIRMED：原生 Result 为 AgentSetupTimeoutError，calls=tools=0，无有效官方评分。'],
        '无决策轨迹，不能分析为模型没有安装依赖或不懂题。',
        '只在同一真实 Python/容器中复核安装命令和缓存身份，不生成、不重新派发模型 Trial。')
