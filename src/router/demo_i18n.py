"""Per-locale string catalog for the two static demos (`/demo/` en,
`/ko/demo/` ko).

Root fix for the demo locale-branch bug: the build used to serve one
locale-neutral body to both demos, so English and Korean copy mixed. Every
reader-facing string now lives here with an explicit ``en`` and ``ko`` side;
``dashboard.py`` carries ``@@key@@`` markers that :func:`render_demo_prose`
resolves per locale, and the measured tab reads :func:`measured_payload`
through an injected ``window.__M_STR__``.

Completeness is enforced (:func:`validate`): every key needs a non-empty
en+ko, a *shared* key (identifier/command/code value) must be identical on
both sides, and a non-shared key must actually differ — so adding a string
with only one locale filled, or forgetting to translate one, fails the build
instead of silently leaking the wrong language into a demo."""
from __future__ import annotations
import re

_HANGUL = re.compile(r"[\uac00-\ud7a3]")

LOCALES = ("en", "ko")

# Keys whose value is a shared identifier/command/code token — intentionally
# identical across locales (ko == en).
SHARED_KEYS = {'k055', 'k115', 'k144', 'k122', 'k005', 'k215', 'k157', 'k007', 'k219', 'k151', 'k145', 'k178', 'k104', 'k100', 'k001', 'k009', 'k023', 'k221', 'k210', 'k208', 'k048', 'k217', 'k028', 'k162'}

# Keys whose original dashboard text was Korean (the leak): en is a new
# translation, ko is the original Korean.
KO_ORIGIN_KEYS = {'k118', 'k127', 'k116', 'k121', 'k117', 'k120', 'k159', 'k126', 'k128', 'k180', 'k132'}

DEMO_STRINGS = {
    'k000': {
        'en': 'cost-router · offline routing demo',
        'ko': 'cost-router · 오프라인 라우팅 데모',
    },
    'k001': {
        'en': 'cost-router',
        'ko': 'cost-router',
    },
    'k002': {
        'en': 'Cost-aware model routing over Microsoft Foundry &middot; offline demo',
        'ko': 'Microsoft Foundry 위의 비용 인지 모델 라우팅 &middot; 오프라인 데모',
    },
    'k003': {
        'en': 'checking&#8230;',
        'ko': '확인 중&#8230;',
    },
    'k004': {
        'en': 'policy &mdash;',
        'ko': '정책 &mdash;',
    },
    'k005': {
        'en': 'offline projection &middot; labels.measured=false',
        'ko': 'offline projection &middot; labels.measured=false',
    },
    'k006': {
        'en': 'Offline replay',
        'ko': '오프라인 리플레이',
    },
    'k007': {
        'en': 'measured=false',
        'ko': 'measured=false',
    },
    'k008': {
        'en': 'Measured run &middot; 03D',
        'ko': '실측 런 &middot; 03D',
    },
    'k009': {
        'en': 'measured=true',
        'ko': 'measured=true',
    },
    'k010': {
        'en': 'The question',
        'ko': '질문',
    },
    'k011': {
        'en': 'Can we cut inference cost ',
        'ko': '추론 비용을',
    },
    'k012': {
        'en': 'without losing coverage',
        'ko': '커버리지를 잃지 않고',
    },
    'k013': {
        'en': '? Route cheap-first &mdash;\n      try the cheapest capable model, and escalate to a stronger one only when the cheap one fails.',
        'ko': '줄일 수 있을까? 싼 모델 먼저 &mdash; 통과할 만한 가장 싼 모델을 먼저 시도하고, 실패할 때만 더 강한 모델로 에스컬레이션한다.',
    },
    'k014': {
        'en': '&#9654;&nbsp; Run replay',
        'ko': '&#9654;&nbsp; 리플레이 실행',
    },
    'k015': {
        'en': ' full synthetic workload (100 tasks)',
        'ko': '합성 워크로드 전체 (100개 과제)',
    },
    'k016': {
        'en': 'idle',
        'ko': '대기',
    },
    'k017': {
        'en': 'lower cost',
        'ko': '더 낮은 비용',
    },
    'k018': {
        'en': '&mdash; run a replay to project savings against an all-premium baseline.',
        'ko': '&mdash; 리플레이를 실행해 all-premium 기준선 대비 절감을 투영한다.',
    },
    'k019': {
        'en': 'Savings depend on workload mix and placeholder pricing &mdash; this is one synthetic run, not a guaranteed number.',
        'ko': '절감은 워크로드 구성과 placeholder 요율에 좌우된다 &mdash; 이건 합성 1회 실행이지 보장된 수치가 아니다.',
    },
    'k020': {
        'en': 'Reproduction complete',
        'ko': '재현 완료',
    },
    'k021': {
        'en': 'Reproduction passed',
        'ko': '재현 통과',
    },
    'k022': {
        'en': '&mdash; tasks &middot; replay verified &middot; ',
        'ko': '&mdash; 과제 &middot; replay 검증됨 &middot;',
    },
    'k023': {
        'en': 'measured=false',
        'ko': 'measured=false',
    },
    'k024': {
        'en': 'Inspect a routing trace',
        'ko': '라우팅 트레이스 살펴보기',
    },
    'k025': {
        'en': 'View methodology',
        'ko': '방법론 보기',
    },
    'k026': {
        'en': '&#9733;&nbsp;Useful? Star it on GitHub',
        'ko': '&#9733;&nbsp;쓸모 있었나요? GitHub에서 Star를 눌러주세요',
    },
    'k027': {
        'en': 'This offline reproduction is a deterministic projection over synthetic data\n      (',
        'ko': '이 오프라인 재현은 합성 데이터에 대한 결정론적 투영이다 (',
    },
    'k028': {
        'en': 'measured=false',
        'ko': 'measured=false',
    },
    'k029': {
        'en': ') &mdash; only a fresh live call ever earns a measured label. The\n      Star link just opens GitHub; nothing here stars the repo for you.',
        'ko': ') &mdash; 실측 라벨은 오직 새 라이브 호출만이 얻는다. Star 링크는 GitHub를 열 뿐이며, 여기서 저장소에 Star를 눌러주지는 않는다.',
    },
    'k030': {
        'en': 'The one task that makes it obvious',
        'ko': '한눈에 드러나는 그 한 과제',
    },
    'k031': {
        'en': 'Spotlight ',
        'ko': '스포트라이트',
    },
    'k032': {
        'en': 'The single task where cheap-first routing beat the all-premium arm by the widest margin &mdash;\n      same task, same checks, one picked the cheapest model that passed.',
        'ko': '싼 모델 먼저 라우팅이 all-premium arm을 가장 크게 앞선 그 한 과제 &mdash; 같은 과제, 같은 검사, 한쪽은 통과하는 가장 싼 모델을 골랐다.',
    },
    'k033': {
        'en': 'routed &middot; cost-aware',
        'ko': '라우팅 &middot; 비용 인지',
    },
    'k034': {
        'en': 'cheaper',
        'ko': '더 저렴',
    },
    'k035': {
        'en': 'naive &middot; premium on every task',
        'ko': '나이브 &middot; 모든 과제에 프리미엄',
    },
    'k036': {
        'en': 'One synthetic task, placeholder pricing &mdash; an offline projection, not a measured saving.',
        'ko': '합성 과제 1건, placeholder 요율 &mdash; 오프라인 투영이지 실측 절감이 아니다.',
    },
    'k037': {
        'en': 'The 5-minute wow',
        'ko': '5분 만의 감탄',
    },
    'k038': {
        'en': 'One problem, four ways ',
        'ko': '한 문제, 네 가지 방식',
    },
    'k039': {
        'en': 'Pick a task. The ',
        'ko': '과제를 하나 고르세요. 같은',
    },
    'k040': {
        'en': 'same problem',
        'ko': '문제',
    },
    'k041': {
        'en': ' is sent four ways &mdash; the cheapest model, the premium\n      model, an ensemble that fans out to all of them, and the cost-aware router that escalates cheap-first.\n      Watch ',
        'ko': '를 네 가지로 보낸다 &mdash; 가장 싼 모델, 프리미엄 모델, 전부로 팬아웃하는 앙상블, 그리고 싼 모델 먼저 에스컬레이션하는 비용 인지 라우터. 각각의',
    },
    'k042': {
        'en': 'cost',
        'ko': '비용',
    },
    'k043': {
        'en': 'latency',
        'ko': '지연',
    },
    'k044': {
        'en': ', and ',
        'ko': ', 그리고',
    },
    'k045': {
        'en': 'accuracy',
        'ko': '정확도',
    },
    'k046': {
        'en': ' fill in for each.',
        'ko': '가 채워지는 걸 지켜보세요.',
    },
    'k047': {
        'en': 'Cost &amp; accuracy reuse the same offline machinery as every other panel (',
        'ko': '비용 &amp; 정확도는 다른 모든 패널과 같은 오프라인 기계를 재사용한다 (',
    },
    'k048': {
        'en': 'measured = false',
        'ko': 'measured = false',
    },
    'k049': {
        'en': ').\n      Latency is an ',
        'ko': '). 지연은 토큰 수에서 뽑은',
    },
    'k050': {
        'en': 'illustrative projection',
        'ko': '예시용 투영',
    },
    'k051': {
        'en': ' from token counts &mdash; not wall-clock; a live run is where real timings come from.',
        'ko': '이다 &mdash; 실측 벽시계 시간이 아니다; 실제 타이밍은 라이브 실행에서 나온다.',
    },
    'k052': {
        'en': 'Live cockpit &mdash; the only place paid runs happen',
        'ko': '라이브 콕핏 &mdash; 유일하게 유료 실행이 일어나는 곳',
    },
    'k053': {
        'en': 'Measure it live ',
        'ko': '라이브로 측정',
    },
    'k054': {
        'en': 'This panel is served by ',
        'ko': '이 패널은',
    },
    'k055': {
        'en': 'cost-router dashboard --live',
        'ko': 'cost-router dashboard --live',
    },
    'k056': {
        'en': ' on your machine. It reads your\n      Foundry connection from the environment (',
        'ko': '이 당신의 머신에서 서빙한다. 환경에서 Foundry 연결을 읽어 (',
    },
    'k057': {
        'en': 'no credential fields here',
        'ko': '자격증명 입력란은 여기 없다',
    },
    'k058': {
        'en': '), shows the exact prompts and a\n      dry-run cost, and only spends after ',
        'ko': '), 정확한 프롬프트와 드라이런 비용을 보여주고, 오직',
    },
    'k059': {
        'en': 'you',
        'ko': '당신',
    },
    'k060': {
        'en': ' click ',
        'ko': '이',
    },
    'k061': {
        'en': 'approve &amp; run',
        'ko': '승인 후 실행',
    },
    'k062': {
        'en': '. The public site never renders it.',
        'ko': '을 누른 뒤에만 비용을 쓴다. 공개 사이트는 이 패널을 절대 렌더하지 않는다.',
    },
    'k063': {
        'en': '1 &middot; Connection',
        'ko': '1 &middot; 연결',
    },
    'k064': {
        'en': 'loading status&#8230;',
        'ko': '상태 로딩&#8230;',
    },
    'k065': {
        'en': '2 &middot; Prompts &amp; dry-run (no calls yet)',
        'ko': '2 &middot; 프롬프트 &amp; 드라이런 (아직 호출 없음)',
    },
    'k066': {
        'en': 'loading catalog&#8230;',
        'ko': '카탈로그 로딩&#8230;',
    },
    'k067': {
        'en': '3 &middot; Run gate &mdash; this button is the human approval',
        'ko': '3 &middot; 실행 게이트 &mdash; 이 버튼이 사람의 승인이다',
    },
    'k068': {
        'en': 'loading plan&#8230;',
        'ko': '플랜 로딩&#8230;',
    },
    'k069': {
        'en': 'Budget cap (USD)',
        'ko': '예산 상한 (USD)',
    },
    'k070': {
        'en': ' I approve running this exact plan',
        'ko': '이 플랜 그대로 실행하는 데 동의합니다',
    },
    'k071': {
        'en': 'approve &amp; run',
        'ko': '승인 후 실행',
    },
    'k072': {
        'en': 'The run halts at the plan-approval and budget gates until they are green.\n      ',
        'ko': '실행은 플랜 승인과 예산 게이트가 초록이 될 때까지 멈춘다.',
    },
    'k073': {
        'en': 'measured=true is only ever shown after completion + a clean snapshot replay',
        'ko': 'measured=true는 오직 완료 + 깨끗한 스냅샷 replay 이후에만 표시된다',
    },
    'k074': {
        'en': ', never at start.',
        'ko': ', 시작 시점엔 절대 아니다.',
    },
    'k075': {
        'en': '4 &middot; Live progress\n        ',
        'ko': '4 &middot; 라이브 진행',
    },
    'k076': {
        'en': 'abort run',
        'ko': '실행 중단',
    },
    'k077': {
        'en': '5 &middot; Snapshot (re-read from disk &mdash; the replay is the check)',
        'ko': '5 &middot; 스냅샷 (디스크에서 다시 읽음 &mdash; replay가 곧 검사다)',
    },
    'k078': {
        'en': 'Pick your fleet',
        'ko': '플릿 선택',
    },
    'k079': {
        'en': 'Fleet &amp; live routing ',
        'ko': '플릿 &amp; 라이브 라우팅',
    },
    'k080': {
        'en': 'These are the Foundry deployments registered in your fleet file. Choose which model plays each\n      role &mdash; the ',
        'ko': '당신의 플릿 파일에 등록된 Foundry 배포들이다. 각 역할을 맡을 모델을 고르세요 &mdash;',
    },
    'k081': {
        'en': 'router (main)',
        'ko': '라우터(main)',
    },
    'k082': {
        'en': ', the ',
        'ko': ', ',
    },
    'k083': {
        'en': 'cheapest',
        'ko': '가장 싼',
    },
    'k084': {
        'en': ' floor, the ',
        'ko': '바닥,',
    },
    'k085': {
        'en': 'premium',
        'ko': '프리미엄',
    },
    'k086': {
        'en': ' ceiling, and the\n      ',
        'ko': '천장, 그리고 팬아웃하는',
    },
    'k087': {
        'en': 'ensemble',
        'ko': '앙상블',
    },
    'k088': {
        'en': ' that fans out. The exact command to run ',
        'ko': '. 당신이 고른',
    },
    'k089': {
        'en': 'your',
        'ko': '선택',
    },
    'k090': {
        'en': ' selection live is generated below.',
        'ko': '을 라이브로 실행할 정확한 명령이 아래에 생성된다.',
    },
    'k091': {
        'en': 'loading fleet&#8230;',
        'ko': '플릿 로딩&#8230;',
    },
    'k092': {
        'en': 'Router (main)',
        'ko': '라우터(main)',
    },
    'k093': {
        'en': 'Cheapest floor',
        'ko': '가장 싼 바닥',
    },
    'k094': {
        'en': 'Premium ceiling',
        'ko': '프리미엄 천장',
    },
    'k095': {
        'en': 'Ensemble / fan-out',
        'ko': '앙상블 / 팬아웃',
    },
    'k096': {
        'en': 'Run selection (recorded)',
        'ko': '선택 실행(기록됨)',
    },
    'k097': {
        'en': 'Run YOUR selection live (measured = true)',
        'ko': '당신의 선택을 라이브로 실행 (measured = true)',
    },
    'k098': {
        'en': 'Three strategies, one workload',
        'ko': '세 전략, 하나의 워크로드',
    },
    'k099': {
        'en': 'Each single-tier strategy fails on one axis. Only the cost-aware mix wins on both cost and coverage.',
        'ko': '단일 티어 전략은 저마다 한 축에서 실패한다. 비용과 커버리지 두 축 모두에서 이기는 건 비용 인지 믹스뿐이다.',
    },
    'k100': {
        'en': 'all-mini',
        'ko': 'all-mini',
    },
    'k101': {
        'en': 'cheapest tier on every task',
        'ko': '모든 과제에 가장 싼 티어',
    },
    'k102': {
        'en': 'coverage &mdash;',
        'ko': '커버리지 &mdash;',
    },
    'k103': {
        'en': 'cheapest &mdash; but the cheap tier fails the hard tasks',
        'ko': '가장 싸다 &mdash; 하지만 싼 티어는 어려운 과제를 실패한다',
    },
    'k104': {
        'en': 'all-premium',
        'ko': 'all-premium',
    },
    'k105': {
        'en': 'premium model on every task',
        'ko': '모든 과제에 프리미엄 모델',
    },
    'k106': {
        'en': 'coverage &mdash;',
        'ko': '커버리지 &mdash;',
    },
    'k107': {
        'en': 'holds coverage &mdash; but the most expensive',
        'ko': '커버리지는 유지 &mdash; 하지만 가장 비싸다',
    },
    'k108': {
        'en': 'cost-aware mix',
        'ko': '비용 인지 믹스',
    },
    'k109': {
        'en': 'cheap-first, escalate only the hard tasks',
        'ko': '싼 모델 먼저, 어려운 과제만 에스컬레이션',
    },
    'k110': {
        'en': '&#10003; recommended',
        'ko': '&#10003; 권장',
    },
    'k111': {
        'en': 'coverage &mdash;',
        'ko': '커버리지 &mdash;',
    },
    'k112': {
        'en': 'the only both-win: full coverage below premium cost',
        'ko': '유일한 양쪽 승리: 프리미엄 비용 아래에서 완전한 커버리지',
    },
    'k113': {
        'en': 'Cost &times; coverage &mdash; the trade-off frontier',
        'ko': '비용 &times; 커버리지 &mdash; 트레이드오프 프론티어',
    },
    'k114': {
        'en': 'run a replay&#8230;',
        'ko': '리플레이 실행&#8230;',
    },
    'k115': {
        'en': 'single-call',
        'ko': 'single-call',
    },
    'k116': {
        'en': '(blue dot) = a single-call routing layer that picks a model',
        'ko': ' (파란 점) = 프롬프트마다\n        모델을 ',
    },
    'k117': {
        'en': 'once',
        'ko': '한 번',
    },
    'k118': {
        'en': 'per prompt is the general form &mdash; it commits up front with no escalation, so coverage is low. The observe-then-escalate',
        'ko': ' 고르는 단일 호출 라우팅 레이어의 일반형 &mdash; 미리 고르고 에스컬레이션이 없어\n        커버리지가 낮습니다. 관찰-후-에스컬레이션하는 ',
    },
    'k119': {
        'en': 'cost-aware mix',
        'ko': '비용 인지 믹스',
    },
    'k120': {
        'en': 'fills coverage at a comparable cost.',
        'ko': '가 비슷한 비용으로 커버리지를 채웁니다.\n        ',
    },
    'k121': {
        'en': 'Experiment 07 &rarr;',
        'ko': '실험 07 &rarr;',
    },
    'k122': {
        'en': 'measured=false',
        'ko': 'measured=false',
    },
    'k123': {
        'en': 'Run a replay to compare all-mini vs all-premium vs the cost-aware mix &mdash; each single-tier strategy fails on one axis; only the mix keeps full coverage below premium cost.',
        'ko': '리플레이를 실행해 all-mini vs all-premium vs 비용 인지 믹스를 비교한다 &mdash; 단일 티어 전략은 저마다 한 축에서 실패하고, 믹스만이 프리미엄 비용 아래에서 완전한 커버리지를 지킨다.',
    },
    'k124': {
        'en': 'experiments',
        'ko': '실험',
    },
    'k125': {
        'en': 'Experiments &mdash; click for the metrics',
        'ko': '실험 &mdash; 눌러서 메트릭 보기',
    },
    'k126': {
        'en': 'Click each experiment for cost &middot; coverage &middot;',
        'ko': '각 실험을 눌러 비용 &middot; 커버리지 &middot; ',
    },
    'k127': {
        'en': 'ensemble fan-out tax',
        'ko': '앙상블 팬아웃 세금',
    },
    'k128': {
        'en': '&middot; reproducibility contract. The numbers are Azure Foundry-shaped offline metrics (labels.measured=false).',
        'ko': ' &middot; 재현성 계약을\n      확인하세요. 수치는 Azure Foundry 형태의 오프라인 메트릭입니다 (labels.measured=false).',
    },
    'k129': {
        'en': 'loading experiments&#8230;',
        'ko': '실험 로딩&#8230;',
    },
    'k130': {
        'en': 'historical',
        'ko': '이력',
    },
    'k131': {
        'en': 'Historical dashboard',
        'ko': '기록 대시보드',
    },
    'k132': {
        'en': 'Recorded history of experiment runs (metrics history store). Each experiment run on the live server appends one row &mdash; the static demo shows a per-experiment baseline snapshot.',
        'ko': '기록된 실험 실행 이력 (metrics history store). 라이브 서버에서 실험을 실행할 때마다\n      한 줄씩 누적됩니다 &mdash; 정적 데모에서는 실험별 기준 스냅샷을 보여줍니다.',
    },
    'k133': {
        'en': 'recorded',
        'ko': '기록됨',
    },
    'k134': {
        'en': 'experiment',
        'ko': '실험',
    },
    'k135': {
        'en': 'coverage',
        'ko': '커버리지',
    },
    'k136': {
        'en': 'routed',
        'ko': '라우팅',
    },
    'k137': {
        'en': 'saved',
        'ko': '절감',
    },
    'k138': {
        'en': 'fan-out tax',
        'ko': '팬아웃 세금',
    },
    'k139': {
        'en': 'ratio',
        'ko': '배수',
    },
    'k140': {
        'en': 'contract',
        'ko': '계약',
    },
    'k141': {
        'en': 'loading history&#8230;',
        'ko': '이력 로딩&#8230;',
    },
    'k142': {
        'en': 'Coverage cliff &mdash; deleting the safety net',
        'ko': '커버리지 절벽 &mdash; 안전망을 지우기',
    },
    'k143': {
        'en': 'A different policy, same workload. Naively deleting the expensive fallback models (',
        'ko': '다른 정책, 같은 워크로드. 비싼 폴백 모델(',
    },
    'k144': {
        'en': 'deep-reasoner',
        'ko': 'deep-reasoner',
    },
    'k145': {
        'en': 'premium-max',
        'ko': 'premium-max',
    },
    'k146': {
        'en': ') looks cheaper &mdash; but silently drops the tasks only they could pass.',
        'ko': ')을 무심코 지우면 더 싸 보인다 &mdash; 하지만 그 모델만 통과할 수 있던 과제를 조용히 떨군다.',
    },
    'k147': {
        'en': 'seed policy',
        'ko': 'seed 정책',
    },
    'k148': {
        'en': 'keeps the expensive fallback',
        'ko': '비싼 폴백을 유지',
    },
    'k149': {
        'en': 'routed &mdash;',
        'ko': '라우팅 &mdash;',
    },
    'k150': {
        'en': 'full coverage &mdash; the fallback catches the hard tasks',
        'ko': '완전한 커버리지 &mdash; 폴백이 어려운 과제를 잡아낸다',
    },
    'k151': {
        'en': 'cost-cut',
        'ko': 'cost-cut',
    },
    'k152': {
        'en': 'deletes the expensive fallback',
        'ko': '비싼 폴백을 지운다',
    },
    'k153': {
        'en': 'routed &mdash;',
        'ko': '라우팅 &mdash;',
    },
    'k154': {
        'en': 'looks cheaper &mdash; but a third of tasks lost a model that passes',
        'ko': '더 싸 보인다 &mdash; 하지만 과제의 3분의 1이 통과하던 모델을 잃었다',
    },
    'k155': {
        'en': "Cost-cut's routed bill is lower only because it stopped covering hard tasks &mdash; that is dropped work, not savings. Cost is comparable only at fixed coverage.",
        'ko': 'cost-cut의 라우팅 청구액이 낮은 건 어려운 과제 커버를 멈췄기 때문일 뿐 &mdash; 그건 절감이 아니라 버려진 작업이다. 비용은 커버리지를 고정했을 때만 비교 가능하다.',
    },
    'k156': {
        'en': 'Deterministic policy regression over shared synthetic signals (100 tasks) &mdash; an offline projection, ',
        'ko': '공유 합성 신호(100개 과제)에 대한 결정론적 정책 회귀 &mdash; 오프라인 투영,',
    },
    'k157': {
        'en': 'measured = false',
        'ko': 'measured = false',
    },
    'k158': {
        'en': '. See the lab notebook: ',
        'ko': '. 랩 노트북 참고:',
    },
    'k159': {
        'en': 'Experiment 03 &middot; coverage cliff',
        'ko': '실험 03 &middot; 커버리지 절벽',
    },
    'k160': {
        'en': 'Fan-out dial &mdash; the ensemble tax is a knob',
        'ko': '팬아웃 다이얼 &mdash; 앙상블 세금은 손잡이다',
    },
    'k161': {
        'en': "Same ensemble workload, one lever: the budget gate's ",
        'ko': '같은 앙상블 워크로드, 레버 하나: 예산 게이트의',
    },
    'k162': {
        'en': 'compare_min_value',
        'ko': 'compare_min_value',
    },
    'k163': {
        'en': '. Raise it and the router fans out on fewer tasks. Coverage and savings stay flat &mdash; only the ensemble tax moves. Experiment 05 (fan out all) vs 06 (fan out none).',
        'ko': '. 이걸 올리면 라우터는 더 적은 과제에서 팬아웃한다. 커버리지와 절감은 평평하게 유지되고 &mdash; 앙상블 세금만 움직인다. 실험 05(전부 팬아웃) vs 06(전혀 팬아웃 안 함).',
    },
    'k164': {
        'en': '&#9646; ensemble tax',
        'ko': '&#9646; 앙상블 세금',
    },
    'k165': {
        'en': ' (collapses)',
        'ko': '(무너짐)',
    },
    'k166': {
        'en': '&ndash;&ndash; coverage',
        'ko': '&ndash;&ndash; 커버리지',
    },
    'k167': {
        'en': ' (flat)',
        'ko': '(평평)',
    },
    'k168': {
        'en': '&ndash;&ndash; savings vs naive',
        'ko': '&ndash;&ndash; 나이브 대비 절감',
    },
    'k169': {
        'en': ' (flat)',
        'ko': '(평평)',
    },
    'k170': {
        'en': 'fan-out (compare)',
        'ko': '팬아웃(compare)',
    },
    'k171': {
        'en': 'coverage',
        'ko': '커버리지',
    },
    'k172': {
        'en': 'savings',
        'ko': '절감',
    },
    'k173': {
        'en': 'ensemble tax',
        'ko': '앙상블 세금',
    },
    'k174': {
        'en': 'fan-out $',
        'ko': '팬아웃 $',
    },
    'k175': {
        'en': 'tax &times;',
        'ko': '세금 &times;',
    },
    'k176': {
        'en': 'On this deterministic projection fan-out finds the same cheapest-passing winner ordered escalation already reaches &mdash; so the tax buys nothing here. Dial it to zero and keep every win. (Best-of-N can lift quality in a real system; this projection does not model that, so measure the lift before paying.)',
        'ko': "이 결정론적 투영에서 팬아웃은 ordered 에스컬레이션이 이미 도달하는 것과 같은 '통과하는 가장 싼' 승자를 찾는다 &mdash; 그래서 여기서 세금은 아무것도 사지 못한다. 0으로 내리고 모든 승리를 지켜라. (실제 시스템에서 best-of-N은 품질을 끌어올릴 수 있다; 이 투영은 그걸 모델링하지 않으니, 비용을 치르기 전에 그 향상을 측정하라.)",
    },
    'k177': {
        'en': 'Offline sweep over the bundled ensemble workload &mdash; ',
        'ko': '번들된 앙상블 워크로드에 대한 오프라인 스윕 &mdash;',
    },
    'k178': {
        'en': 'measured = false',
        'ko': 'measured = false',
    },
    'k179': {
        'en': '. See the lab notebook: ',
        'ko': '. 랩 노트북 참고:',
    },
    'k180': {
        'en': 'Experiment 06 &middot; adaptive fan-out dial',
        'ko': '실험 06 &middot; 적응형 팬아웃 다이얼',
    },
    'k181': {
        'en': 'At a glance',
        'ko': '한눈에',
    },
    'k182': {
        'en': 'Headline numbers for this run.',
        'ko': '이번 실행의 헤드라인 수치.',
    },
    'k183': {
        'en': 'tasks',
        'ko': '과제',
    },
    'k184': {
        'en': 'coverage',
        'ko': '커버리지',
    },
    'k185': {
        'en': 'single-route',
        'ko': '단일 경로',
    },
    'k186': {
        'en': 'ensemble',
        'ko': '앙상블',
    },
    'k187': {
        'en': 'avg $/task',
        'ko': '과제당 평균 $',
    },
    'k188': {
        'en': 'single-route',
        'ko': '단일 경로',
    },
    'k189': {
        'en': ' &mdash; try candidates cheapest-first and take the first one that passes.',
        'ko': '&mdash; 가장 싼 후보부터 시도해 처음 통과하는 하나를 취한다.',
    },
    'k190': {
        'en': 'ensemble',
        'ko': '앙상블',
    },
    'k191': {
        'en': ' &mdash; evaluate several models and keep the best; reserved for higher-value tasks.',
        'ko': '&mdash; 여러 모델을 평가해 최선을 남긴다; 가치가 높은 과제에만 배정한다.',
    },
    'k192': {
        'en': ' Breakdown ',
        'ko': '분해',
    },
    'k193': {
        'en': 'cost by class &middot; model usage &middot; routing modes',
        'ko': '클래스별 비용 &middot; 모델 사용 &middot; 라우팅 모드',
    },
    'k194': {
        'en': 'Cost by task class &mdash; routed vs naive',
        'ko': '작업 클래스별 비용 &mdash; 라우팅 vs 나이브',
    },
    'k195': {
        'en': 'run a replay&#8230;',
        'ko': '리플레이 실행&#8230;',
    },
    'k196': {
        'en': 'Model usage &mdash; tasks &amp; routed cost',
        'ko': '모델 사용 &mdash; 과제 &amp; 라우팅 비용',
    },
    'k197': {
        'en': 'run a replay&#8230;',
        'ko': '리플레이 실행&#8230;',
    },
    'k198': {
        'en': 'Routing mode',
        'ko': '라우팅 모드',
    },
    'k199': {
        'en': 'run a replay&#8230;',
        'ko': '리플레이 실행&#8230;',
    },
    'k200': {
        'en': 'Reason',
        'ko': '이유',
    },
    'k201': {
        'en': 'run a replay&#8230;',
        'ko': '리플레이 실행&#8230;',
    },
    'k202': {
        'en': 'What each column means',
        'ko': '각 열의 의미',
    },
    'k203': {
        'en': 'task',
        'ko': '과제',
    },
    'k204': {
        'en': ' &mdash; synthetic task id.',
        'ko': '&mdash; 합성 과제 id.',
    },
    'k205': {
        'en': 'class',
        'ko': '클래스',
    },
    'k206': {
        'en': ' &mdash; task type: plan &middot; generate &middot; test &middot; validate &middot; repo_patch.',
        'ko': '&mdash; 작업 유형: plan &middot; generate &middot; test &middot; validate &middot; repo_patch.',
    },
    'k207': {
        'en': 'mode',
        'ko': '모드',
    },
    'k208': {
        'en': 'ordered',
        'ko': 'ordered',
    },
    'k209': {
        'en': ' = cheapest-first, take the first clean one &middot; ',
        'ko': '= 가장 싼 것 먼저, 처음으로 깨끗한 하나를 취함 &middot;',
    },
    'k210': {
        'en': 'compare',
        'ko': 'compare',
    },
    'k211': {
        'en': ' = ensemble, keep the best.',
        'ko': '= 앙상블, 최선을 남김.',
    },
    'k212': {
        'en': 'chosen',
        'ko': '선택',
    },
    'k213': {
        'en': ' &mdash; placeholder model that handled the task.',
        'ko': '&mdash; 과제를 처리한 placeholder 모델.',
    },
    'k214': {
        'en': 'reason',
        'ko': '이유',
    },
    'k215': {
        'en': 'clean-first',
        'ko': 'clean-first',
    },
    'k216': {
        'en': ' top pick passed &middot; ',
        'ko': '상위 선택이 통과 &middot;',
    },
    'k217': {
        'en': 'escalated',
        'ko': 'escalated',
    },
    'k218': {
        'en': ' cheaper failed, moved up &middot; ',
        'ko': '싼 게 실패해 위로 올림 &middot;',
    },
    'k219': {
        'en': 'compared',
        'ko': 'compared',
    },
    'k220': {
        'en': ' ensemble winner &middot; ',
        'ko': '앙상블 승자 &middot;',
    },
    'k221': {
        'en': 'tie-broken',
        'ko': 'tie-broken',
    },
    'k222': {
        'en': ' settled by cost.',
        'ko': '비용으로 결정.',
    },
    'k223': {
        'en': 'cost',
        'ko': '비용',
    },
    'k224': {
        'en': 'projected USD for this task (offline, not measured).',
        'ko': '이 과제의 투영 USD(오프라인, 실측 아님).',
    },
    'k225': {
        'en': ' Per-task routing trace ',
        'ko': '과제별 라우팅 트레이스',
    },
    'k226': {
        'en': 'every task, streamed live',
        'ko': '모든 과제, 라이브 스트리밍',
    },
    'k227': {
        'en': 'task',
        'ko': '과제',
    },
    'k228': {
        'en': 'class',
        'ko': '클래스',
    },
    'k229': {
        'en': 'mode',
        'ko': '모드',
    },
    'k230': {
        'en': 'chosen',
        'ko': '선택',
    },
    'k231': {
        'en': 'reason',
        'ko': '이유',
    },
    'k232': {
        'en': 'cost',
        'ko': '비용',
    },
    'k233': {
        'en': ' Policy &amp; model tiers ',
        'ko': '정책 &amp; 모델 티어',
    },
    'k234': {
        'en': 'class &#8594; candidates, cheapest first',
        'ko': '클래스 &#8594; 후보, 가장 싼 것부터',
    },
    'k235': {
        'en': 'loading&#8230;',
        'ko': '로딩&#8230;',
    },
    'k236': {
        'en': 'Model tiers &mdash; what these names mean',
        'ko': '모델 티어 &mdash; 이 이름들의 의미',
    },
    'k237': {
        'en': 'loading&#8230;',
        'ko': '로딩&#8230;',
    },
    'k238': {
        'en': 'Generic placeholder tiers &mdash; not real product names. They stand in for a\n        lightweight/high-volume model, an efficient coder, a balanced general model, a deliberate\n        reasoner, and a premium frontier model.',
        'ko': '일반 placeholder 티어 &mdash; 실제 제품명이 아니다. 경량/대용량 모델, 효율적인 코더, 균형 잡힌 범용 모델, 신중한 추론기, 프리미엄 프론티어 모델을 대신한다.',
    },
    'k239': {
        'en': 'Numbers are an offline projection over synthetic data &mdash; not measured. Model names are generic placeholders.',
        'ko': '수치는 합성 데이터에 대한 오프라인 투영이다 &mdash; 실측이 아니다. 모델명은 일반 placeholder다.',
    },
}

MEASURED = {
    'en': {
        'tabOffline': 'Offline replay',
        'tabMeasured': 'Measured run · 03D',
        'badgeOff': 'offline projection · labels.measured=false',
        'badgeMeas': 'sealed 03D · labels.measured=true',
        'eyebrow': 'Measured run · sealed 03D snapshot',
        'title': 'What the router actually picked — one real measured run',
        'sub': 'Four arms (three routing modes + the direct-premium baseline) over the same 24 coding tasks at n=3 on real Azure AI Foundry — 288 cells, sealed and replay-verified byte-identical. Rendered read-only from the masked published.json bundle: aggregates only, no prompts, endpoints, or tenant ids.',
        'lblCoverage': 'coverage',
        'lblUnpriced': 'unpriced',
        'lblReplay': 'replay verified',
        'lblSpend': 'spend',
        'armsTitle': 'Four arms — cost · pass rate · $/pass · grading coverage',
        'armsNote': 'Deployment shown under each arm. Every arm is cost_complete=true (unpriced 0%), every cell priced at pinned rates. Pass rate is task-based (solved/planned); grading coverage is cell-based (measurement completeness) — different denominators.',
        'cCost': 'cost',
        'cPass': 'pass rate',
        'cPerPass': '$/pass',
        'cCov': 'coverage',
        'cells': 'cells',
        'head': 'The cheapest router mode <b>router-cost</b> holds a <b>{qCost}</b> task pass rate while running <b>{cheaper}% cheaper</b> than direct-premium. The pass-rate gap is within <b>{gap}%p</b> — and that gap is entirely due to timeouts (below), not code quality.',
        'domH': 'Most counterintuitive — the quality mode is dominated by direct-premium',
        'domP': "<b>router-quality</b> ({qCostUsd}) is more expensive than <b>direct-premium</b> ({premUsd}) yet lands a lower pass rate ({qQual} &lt; {premQual}). If you want quality, calling direct-premium directly is cheaper and more accurate than the router's quality mode — on this workload. Meanwhile router-cost holds the same {costQual} pass rate at under 1/20 the cost.",
        'setupTitle': 'Setup — what was actually run',
        'setupNote': 'Real deployment and backend identifiers from the sealed run — every name below is verbatim from the masked bundle. (The offline tab keeps synthetic placeholder model names; attaching real names to synthetic data would imply a per-model performance claim.)',
        'setArms': 'Arms',
        'setBackends': 'Backends the router picked',
        'setWorkload': 'Workload',
        'setRun': 'Run conditions',
        'rosterEvidence': 'None of these is a deployment in this run — the four deployments are <span class="mono">{deps}</span>. The router selected these backends from its own managed roster; <b>grok-4-1-fast-reasoning</b> in particular was never deployed to this account, yet Cost mode routed 100% to it.',
        'workloadVal': 'curated-24 · {tasks} tasks × {arms} arms × n={n} = {cells} cells',
        'runVal': 'keyless Entra · sequential dispatch · fixed seed 20260729',
        'backTitle': 'Backend distribution — which model each arm actually reached',
        'backNote': 'Over graded cells only (timeout cells, whose backend never settled, are excluded). Cost mode routed 100% to grok-4-1-fast-reasoning — a skew reproduced across both measured runs (the prior void run and this publishable one). Quality mode uses no Grok at all.',
        'toTitle': '11 timeout cells — shown, not hidden',
        'toNote': "All 11 are HTTP 408 read timeouts, all in the router arms; direct-premium had 0. A timeout cell is handled doubly conservatively — excluded from grading coverage AND counted as a failure — so the router arms' pass rate falls below direct-premium by exactly these timeouts. The 4.17%p gap is a latency-profile difference (router backends p50 ~12–16s vs direct-premium ~4.2s), not code quality.",
        'toByArm': 'By arm',
        'toByTask': 'By task',
        'toArm': 'arm',
        'toTask': 'task',
        'toN': 'timeouts',
        'limTitle': 'Limits — read before generalizing',
        'limits': [
            '<b>24 tasks → evidence_tier directional.</b> A directional signal, not statistical confidence — a statistical conclusion would need ~100 problems.',
            '<b>Single tenant · single region · one measurement.</b> Replay guarantees reproduction, not a population estimate.',
            '<b>Timeouts count against the router arms only.</b> The router backends have longer latency and hit the fixed timeout; direct-premium does not — a latency-profile difference, not code quality.',
            '<b>Do not generalize to other workloads.</b> Limited to this workload · this tenant · this one measurement.',
        ],
        'caveat': 'Sealed snapshot, rendered read-only — changing any number here would break the replay guarantee. Full write-up:',
        'caveatLink': '03D Results',
        'armLbl': {
            'router-cost': 'Cost mode',
            'router-balanced': 'Balanced mode',
            'direct-premium': 'Direct premium',
            'router-quality': 'Quality mode',
        },
    },
    'ko': {
        'tabOffline': '오프라인 재현',
        'tabMeasured': '실측 런 · 03D',
        'badgeOff': 'offline projection · labels.measured=false',
        'badgeMeas': 'sealed 03D · labels.measured=true',
        'eyebrow': '실측 런 · 봉인 03D 스냅샷',
        'title': '라우터가 실제로 고른 것 — 실측 1회',
        'sub': '같은 24개 코딩 과제를 n=3으로 실제 Azure AI Foundry에서 네 arm(라우팅 3모드 + direct-premium 기준선)에 돌린 결과 — 288셀, 봉인, replay로 바이트 동일 검증. 마스킹된 published.json 번들에서 읽기 전용으로 렌더했다: 집계뿐이며 프롬프트·엔드포인트·테넌트 식별자는 없다.',
        'lblCoverage': 'coverage',
        'lblUnpriced': 'unpriced',
        'lblReplay': 'replay verified',
        'lblSpend': 'spend',
        'armsTitle': '네 arm — 비용 · 통과율 · $/pass · 채점 커버리지',
        'armsNote': 'arm 이름 아래에 배포명을 표기했다. 모든 arm이 cost_complete=true(unpriced 0%)이고 셀마다 고정 요율로 가격이 매겨졌다. 통과율은 과제 기준(해결/계획), 채점 커버리지는 셀 기준(측정 완결성) — 분모가 다르다.',
        'cCost': '비용',
        'cPass': '통과율',
        'cPerPass': '$/pass',
        'cCov': '커버리지',
        'cells': '셀',
        'head': '가장 싼 라우터 모드 <b>router-cost</b>는 통과율 <b>{qCost}</b>를 유지하면서 direct-premium 대비 <b>{cheaper}% 저렴</b>하다. 통과율 격차는 <b>{gap}%p</b> 이내이고, 그 격차조차 전부 타임아웃 때문이지(아래) 코드 품질 때문이 아니다.',
        'domH': '가장 반직관적인 발견 — quality 모드가 direct-premium에 지배당한다',
        'domP': '<b>router-quality</b>({qCostUsd})는 <b>direct-premium</b>({premUsd})보다 비싼데도 통과율은 더 낮다({qQual} &lt; {premQual}). 품질을 원한다면 라우터의 quality 모드보다 direct-premium을 직접 부르는 편이 더 싸고 더 정확하다 — 이 워크로드에서는. 한편 router-cost는 같은 {costQual} 통과율을 1/20 미만 비용으로 유지한다.',
        'setupTitle': '실험 구성 — 무엇을 돌렸나',
        'setupNote': '봉인 런의 실제 배포·백엔드 식별자다 — 아래 모든 이름은 마스킹된 번들에서 그대로 가져왔다. (offline 탭은 합성 placeholder 모델명을 유지한다; 합성 데이터에 실제 모델명을 붙이면 모델별 성능 주장이 되기 때문이다.)',
        'setArms': 'Arm 구성',
        'setBackends': '라우터가 고른 백엔드',
        'setWorkload': '워크로드',
        'setRun': '실행 조건',
        'rosterEvidence': '이 중 어느 것도 이번 런의 배포가 아니다 — 배포는 넷뿐이다: <span class="mono">{deps}</span>. 라우터는 이 백엔드들을 자기 관리 로스터에서 골랐다; 특히 <b>grok-4-1-fast-reasoning</b>은 이 계정에 배포된 적이 없는데도 Cost 모드가 100%를 그리로 보냈다.',
        'workloadVal': 'curated-24 · 과제 {tasks}개 × arm {arms}개 × n={n} = {cells}셀',
        'runVal': 'keyless Entra · 순차 디스패치 · 고정 시드 20260729',
        'backTitle': '백엔드 분포 — 각 arm이 실제로 도달한 모델',
        'backNote': '채점된 셀만 대상(백엔드가 확정되지 않은 타임아웃 셀은 제외). Cost 모드는 100%를 grok-4-1-fast-reasoning으로 보냈다 — 이 쏠림은 두 번의 실측 런(직전 void 런과 이 발행 런)에서 재현됐다. quality 모드는 Grok을 전혀 쓰지 않는다.',
        'toTitle': '타임아웃 11셀 — 숨기지 않고 보여준다',
        'toNote': '11셀 전부 HTTP 408 읽기 타임아웃이고 전부 라우터 arm에서 났다. direct-premium은 0. 타임아웃 셀은 이중으로 보수적으로 처리된다 — 채점 커버리지에서 제외되는 동시에 실패로 집계된다 — 그래서 라우터 arm 통과율이 딱 이 타임아웃만큼 direct-premium보다 낮다. 4.17%p 격차는 지연 프로파일 차이(라우터 백엔드 p50 ~12–16초 vs direct-premium ~4.2초)이지 코드 품질이 아니다.',
        'toByArm': 'arm별',
        'toByTask': '과제별',
        'toArm': 'arm',
        'toTask': '과제',
        'toN': '타임아웃',
        'limTitle': '한계 — 일반화 전에 읽어라',
        'limits': [
            '<b>24과제 → evidence_tier directional.</b> 통계적 신뢰가 아니라 방향성 신호다 — 통계적 결론에는 ~100문제가 필요하다.',
            '<b>단일 테넌트 · 단일 리전 · 1회 측정.</b> replay는 재현을 보장하지 모집단 추정을 보장하지 않는다.',
            '<b>타임아웃은 라우터 arm에만 불리하게 집계된다.</b> 라우터 백엔드는 지연이 더 길어 고정 타임아웃에 걸리고 direct-premium은 걸리지 않는다 — 지연 프로파일 차이지 코드 품질이 아니다.',
            '<b>다른 워크로드로 일반화하지 마라.</b> 이 워크로드 · 이 테넌트 · 이 1회 측정에 한정된다.',
        ],
        'caveat': '봉인 스냅샷을 읽기 전용으로 렌더한 것 — 여기 숫자를 바꾸면 replay 보장이 깨진다. 전체 서술:',
        'caveatLink': '03D 결과',
        'armLbl': {
            'router-cost': 'Cost 모드',
            'router-balanced': 'Balanced 모드',
            'direct-premium': '직접 프리미엄',
            'router-quality': 'Quality 모드',
        },
    },
}

EXPERIMENT_I18N = {
    'adaptive': {
        'title': {
            'en': 'Adaptive fan-out dial — drive the ensemble tax to zero, keep the savings',
            'ko': '적응형 팬아웃 다이얼 — 앙상블 세금을 0으로, 절감은 그대로',
        },
        'summary': {
            'en': "Reuses experiment 05's workload unchanged but turns fan-out off by raising the budget gate's compare_min_value above every task's value. Coverage stays at 100% and savings hold at ~47% versus naive, yet the ensemble tax collapses to ~$0.00. On a deterministic offline projection, fan-out picks the same winner ordered escalation already finds — the cheapest passing model — so the tax is pure overhead; the dial recovers all of it with no loss.",
            'ko': '실험 05와 같은 워크로드를 그대로 쓰되, 예산 게이트의 compare_min_value를 모든 태스크 가치보다 높게 올려 팬아웃을 끕니다. 커버리지 100%와 나이브 대비 ~47% 절감은 동일하지만, 앙상블 세금은 ~$0.00으로 무너집니다. 결정론적 오프라인 투영에서 팬아웃은 ordered 에스컬레이션이 이미 찾는 가장 싼 통과 모델과 같은 승자를 고르므로 순수 세금입니다 — 다이얼로 그 세금을 손실 없이 전부 회수합니다.',
        },
    },
    'curated': {
        'title': {
            'en': 'Curated sample — five tasks you can follow by eye',
            'ko': '큐레이션 샘플 — 눈으로 따라가는 5개 태스크',
        },
        'summary': {
            'en': 'Routes a handful of tasks carrying hand-written offline signals — a minimal sample where you can read the data end to end and watch each routing decision by eye.',
            'ko': '손으로 작성한 오프라인 신호가 붙은 소수의 태스크를 라우팅해, 데이터를 처음부터 끝까지 읽으며 라우팅 결정을 눈으로 확인할 수 있는 최소 샘플입니다.',
        },
    },
    'ensemble': {
        'title': {
            'en': 'Ensemble fan-out — take the best, but pay the real cost',
            'ko': '앙상블 팬아웃 — 최선을 뽑되, 진짜 비용을 치른다',
        },
        'summary': {
            'en': "Fans high-value tasks out to every candidate (compare mode) and keeps the best. Because several models pass, best-of-N keeps the cheapest passing model (the sweet spot) and saves versus naive — but fan-out also runs the losers, so it pays 3.7× the winner's cost. That is the ensemble tax. Routing only fans out where the value is high.",
            'ko': '가치가 높은 태스크를 모든 후보에 팬아웃(compare 모드)해 최선을 뽑습니다. 여러 모델이 통과하므로 best-of-N은 가장 싼 통과 모델(스위트 스팟)을 남겨 나이브 대비 절감하지만, 팬아웃은 진 모델까지 실행하므로 승자 비용의 3.7배를 지불합니다 — 이것이 앙상블 세금입니다. 라우팅은 가치가 높은 곳에서만 팬아웃합니다.',
        },
    },
    'hero': {
        'title': {
            'en': 'Same coverage, lower cost — the 30-second hero run',
            'ko': '같은 커버리지, 더 낮은 비용 — 30초 히어로 실행',
        },
        'summary': {
            'en': "Routes 100 synthetic tasks 'cheapest passing model first, escalate only on failure' and compares it against the naive approach of using the premium model on every task.",
            'ko': "합성 워크로드 100건을 '통과하는 가장 싼 모델 먼저, 실패할 때만 상위 모델로' 라우팅해 모든 태스크에 프리미엄 모델을 쓰는 나이브 방식과 비교합니다.",
        },
    },
    'limits': {
        'title': {
            'en': 'No free lunch — the limits of routing',
            'ko': '공짜 점심은 없다 — 라우팅의 한계',
        },
        'summary': {
            'en': "A workload where every task is genuinely hard and only the most expensive model passes. Routing tries the cheap models first, but they all fail and it escalates to the top model, so savings are 0%. Routing does not invent savings that aren't there — it spends honestly on hard work.",
            'ko': '모든 태스크가 진짜 어려워 가장 비싼 모델만 통과하는 워크로드입니다. 라우팅은 싼 모델부터 시도하지만 전부 실패해 최상위 모델로 에스컬레이션하며, 절감은 0%. 라우팅은 없는 절감을 지어내지 않고, 어려운 일엔 정직하게 비용을 씁니다.',
        },
    },
    'single-call': {
        'title': {
            'en': 'Routing layers — pick once vs observe-then-escalate',
            'ko': '라우팅 레이어 — 한 번 고르기 vs 관찰하고 올리기',
        },
        'summary': {
            'en': "Projects 'single-call' routing that picks one model per prompt up front (what the built-in Model Router already does well) as a difficulty-tiered one-shot arm, and compares it on the same axes as this repo's 'observe and escalate only when needed' routing. The one-shot arm commits early and loses coverage; the escalation layer wins that coverage back at the same cost band.",
            'ko': "프롬프트당 모델 하나를 앞서 고르는 '단일 콜' 라우팅(내장 Model Router가 이미 잘 하는 일)을 난이도 기반 원샷 arm으로 투영하고, 이 저장소의 '관찰하고 필요할 때만 올리는' 라우팅과 같은 축에서 비교합니다. 원샷은 앞서 커밋해 커버리지를 잃고, 에스컬레이션 레이어가 같은 비용대에서 그 커버리지를 되찾습니다.",
        },
    },
}


def validate() -> None:
    """Fail loudly if the catalog is incomplete or a locale would leak.

    Enforced invariants (the build calls this before every render):
      * every ``DEMO_STRINGS`` entry has a non-empty ``en`` and ``ko``;
      * a ``SHARED_KEYS`` entry is identical on both sides (a shared identifier);
      * a non-shared entry actually differs (a forgotten translation is an error);
      * no ``en`` value carries Korean (English-demo purity);
      * ``MEASURED`` has both locales with matching keys, equal-length ``limits``
        and an ``armLbl`` for every arm; no ``en`` measured string has Korean;
      * every ``EXPERIMENT_I18N`` entry has en+ko title/summary, en Korean-free.
    """
    for key, pair in DEMO_STRINGS.items():
        en_v, ko_v = pair.get("en", ""), pair.get("ko", "")
        if not en_v or not ko_v:
            raise AssertionError(f"demo string {key!r} missing a locale (en/ko)")
        if _HANGUL.search(en_v):
            raise AssertionError(f"demo string {key!r} en side carries Korean")
        if key in SHARED_KEYS:
            if en_v != ko_v:
                raise AssertionError(f"shared demo string {key!r} differs across locales")
        elif en_v == ko_v:
            raise AssertionError(f"demo string {key!r} is untranslated (en == ko)")

    en_m, ko_m = MEASURED["en"], MEASURED["ko"]
    if set(en_m) != set(ko_m):
        raise AssertionError("MEASURED en/ko key sets differ")
    if len(en_m["limits"]) != len(ko_m["limits"]):
        raise AssertionError("MEASURED limits differ in length across locales")
    arms = set(en_m["armLbl"])
    if arms != set(ko_m["armLbl"]):
        raise AssertionError("MEASURED armLbl arms differ across locales")
    for locale in LOCALES:
        payload = MEASURED[locale]
        for mkey, val in payload.items():
            texts = val if isinstance(val, list) else (
                list(val.values()) if isinstance(val, dict) else [val])
            if locale == "en" and any(_HANGUL.search(t) for t in texts):
                raise AssertionError(f"MEASURED en.{mkey} carries Korean")

    for name, fields in EXPERIMENT_I18N.items():
        for field in ("title", "summary"):
            pair = fields.get(field, {})
            if not pair.get("en") or not pair.get("ko"):
                raise AssertionError(f"experiment {name!r} {field} missing a locale")
            if _HANGUL.search(pair["en"]):
                raise AssertionError(f"experiment {name!r} {field} en carries Korean")


def render_demo_prose(template: str, locale: str) -> str:
    """Resolve every ``@@key@@`` marker in ``template`` to ``locale``.

    Raises if the locale is unknown, a marker has no catalog entry, or any
    marker survives — so a stale template or a dropped key fails the build.
    """
    if locale not in LOCALES:
        raise ValueError(f"unknown demo locale {locale!r} (expected en or ko)")
    validate()
    out = template
    for key, pair in DEMO_STRINGS.items():
        out = out.replace("@@" + key + "@@", pair[locale])
    if "@@" in out:
        leftover = sorted(set(re.findall(r"@@(\w+)@@", out)))
        raise AssertionError(f"unresolved demo markers after render: {leftover}")
    return out


def measured_payload(locale: str) -> dict:
    """Single-locale measured-tab payload injected as ``window.__M_STR__``."""
    if locale not in LOCALES:
        raise ValueError(f"unknown demo locale {locale!r} (expected en or ko)")
    return MEASURED[locale]


def localize_experiments(payload: object, locale: str) -> object:
    """Rewrite experiment ``title``/``summary``/``metrics.title`` in an
    ``/experiments`` or ``/metrics/history`` payload to ``locale``.

    The catalog is the source of truth: an experiment carrying prose with no
    ``EXPERIMENT_I18N`` entry is left untouched, and the caller (the build)
    asserts the English demo JSON is Korean-free, so a missing translation
    fails the build rather than leaking Korean into ``/demo/``.
    """
    if locale not in LOCALES:
        raise ValueError(f"unknown demo locale {locale!r} (expected en or ko)")

    def _apply(entry: dict) -> None:
        name = entry.get("name") or entry.get("experiment")
        fields = EXPERIMENT_I18N.get(name)
        if not fields:
            return
        if "title" in entry and fields.get("title"):
            entry["title"] = fields["title"][locale]
        if "summary" in entry and fields.get("summary"):
            entry["summary"] = fields["summary"][locale]
        metrics = entry.get("metrics")
        if isinstance(metrics, dict) and "title" in metrics and fields.get("title"):
            metrics["title"] = fields["title"][locale]

    if isinstance(payload, dict):
        for coll in ("experiments", "history"):
            items = payload.get(coll)
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, dict):
                        _apply(entry)
    return payload
