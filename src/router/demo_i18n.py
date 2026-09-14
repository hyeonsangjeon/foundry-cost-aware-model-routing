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
        'en': 'cost-router · offline routing demo over synthetic data',
        'ko': 'cost-router · 합성 데이터 오프라인 라우팅 데모',
    },
    'k001': {
        'en': 'cost-router',
        'ko': 'cost-router',
    },
    'k002': {
        'en': 'Cost-aware model routing over Microsoft Foundry &middot; offline demo over synthetic data',
        'ko': 'Microsoft Foundry에서 비용을 고려한 모델 라우팅 &middot; 합성 데이터 오프라인 데모',
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
        'ko': '오프라인 재생',
    },
    'k007': {
        'en': 'measured=false',
        'ko': 'measured=false',
    },
    'k008': {
        'en': 'Measured run &middot; experiment 12',
        'ko': '실측 실행 &middot; 실험 12',
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
        'ko': '추론 비용을 ',
    },
    'k012': {
        'en': 'without losing the task pass rate',
        'ko': '과제 통과율을 잃지 않고 ',
    },
    'k013': {
        'en': '? The task pass rate is the share of tasks that pass their checks; the JSON payloads behind\n      this page still name that field <code>coverage</code>. Route cheap-first &mdash; try the cheapest\n      capable model, and escalate to a stronger one only when the cheap one fails. Every figure below\n      is an offline projection over synthetic data, compared against calling the premium model on\n      every task.',
        'ko': '줄일 수 있을까? 과제 통과율은 검사를 통과한 과제의 비율이고, 이 화면이 읽는 JSON에서는 이 값의 필드 이름이 아직 <code>coverage</code>다. 싼 모델 먼저 &mdash; 통과할 만한 가장 싼 모델을 먼저 시도하고, 실패할 때만 더 강한 모델로 에스컬레이션한다. 아래 수치는 모두 합성 데이터에 대한 오프라인 투영이며, 모든 과제에 프리미엄 모델을 쓰는 방식과 비교한 값이다.',
    },
    'k014': {
        'en': '&#9654;&nbsp; Run replay',
        'ko': '&#9654;&nbsp; 재생 실행',
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
        'en': 'lower cost vs premium on every task',
        'ko': '모든 과제 프리미엄 대비 절감',
    },
    'k018': {
        'en': '&mdash; run a replay to project savings against the all-premium baseline (the premium model on every task).',
        'ko': '&mdash; 재생을 실행해 all-premium 기준선(모든 과제에 프리미엄 모델) 대비 절감을 투영한다.',
    },
    'k019': {
        'en': 'Savings depend on the workload mix and on placeholder pricing &mdash; this is one synthetic run, not a guaranteed number.',
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
        'ko': '&mdash; 과제 &middot; 재생 검증됨 &middot;',
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
        'en': 'Representative task',
        'ko': '대표 과제',
    },
    'k031': {
        'en': 'The widest single-task gap ',
        'ko': '한 과제에서 벌어진 가장 큰 격차',
    },
    'k032': {
        'en': 'The single task where cheap-first routing beat the all-premium arm by the widest margin\n      &mdash; an arm is one routing strategy in the comparison. Same task, same checks; one arm picked\n      the cheapest model that passed.',
        'ko': '싼 모델 먼저 라우팅이 all-premium arm을 가장 크게 앞선 그 한 과제 &mdash; arm은 비교에 쓰인 라우팅 전략 하나를 뜻한다. 같은 과제, 같은 검사에서 한쪽은 통과하는 가장 싼 모델을 골랐다.',
    },
    'k033': {
        'en': 'routed &middot; cheapest-first escalation',
        'ko': '라우팅 &middot; 싼 모델 먼저 올리는 방식',
    },
    'k034': {
        'en': 'cheaper',
        'ko': '더 저렴',
    },
    'k035': {
        'en': 'premium on every task',
        'ko': '모든 과제에 프리미엄',
    },
    'k036': {
        'en': 'One synthetic task at placeholder pricing &mdash; an offline projection, not a measured saving.',
        'ko': '합성 과제 1건, placeholder 요율 &mdash; 오프라인 투영이지 실측 절감이 아니다.',
    },
    'k037': {
        'en': 'Four-way comparison',
        'ko': '네 방식 비교',
    },
    'k038': {
        'en': 'One problem, four routing strategies ',
        'ko': '문제 하나를 네 방식으로',
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
        'en': ' is sent four ways &mdash; the cheapest model, the premium\n      model, an ensemble that fans out to all of them, and the router that tries the cheapest\n      model first and escalates only after a failed check. Watch ',
        'ko': '를 네 가지로 보낸다 &mdash; 가장 싼 모델, 프리미엄 모델, 전부로 팬아웃하는 앙상블, 그리고 싼 모델을 먼저 시도한 뒤 실패를 확인하면 상위 모델을 다시 호출하는 라우터. 각각의',
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
        'en': 'Cost and accuracy reuse the same offline machinery as every other panel (',
        'ko': '비용과 정확도는 다른 모든 패널과 같은 오프라인 기계를 재사용한다 (',
    },
    'k048': {
        'en': 'measured = false',
        'ko': 'measured = false',
    },
    'k049': {
        'en': ').\n      Latency is an ',
        'ko': '). 지연은',
    },
    'k050': {
        'en': 'illustrative projection',
        'ko': '예시용 투영',
    },
    'k051': {
        'en': ' computed from the authored synthetic output and reasoning token estimates for each\n      strategy &mdash; not wall-clock time. Real timings come only from a live measured run.',
        'ko': '이다 &mdash; 각 전략에 대해 작성된 합성 출력 토큰과 추론 토큰 추정치로 계산했으며, 실측 벽시계 시간이 아니다. 실제 타이밍은 라이브 실측 실행에서만 나온다.',
    },
    'k052': {
        'en': 'Live run panel &mdash; the only place paid calls happen',
        'ko': '라이브 실행 패널 &mdash; 유일하게 유료 호출이 일어나는 곳',
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
        'ko': '자격 증명 입력란은 여기 없다',
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
        'ko': 'measured=true는 오직 완료 + 깨끗한 스냅샷 재생 이후에만 표시된다',
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
        'ko': '5 &middot; 스냅샷 (디스크에서 다시 읽음 &mdash; 재생이 곧 검사다)',
    },
    'k078': {
        'en': 'Pick your candidate set',
        'ko': '후보 모델 세트 고르기',
    },
    'k079': {
        'en': 'Candidate set &amp; role assignment ',
        'ko': '후보 모델 세트 &amp; 역할 지정',
    },
    'k080': {
        'en': 'These are the Foundry deployments registered in your candidate-set file. Choose which model\n      plays each role &mdash; the ',
        'ko': '당신의 후보 모델 세트 파일에 등록된 Foundry 배포들이다. 각 역할을 맡을 모델을 고르세요 &mdash;',
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
        'en': 'loading the candidate set&#8230;',
        'ko': '후보 모델 세트 로딩&#8230;',
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
        'en': 'Run your selection live (measured = true)',
        'ko': '당신의 선택을 라이브로 실행 (measured = true)',
    },
    'k098': {
        'en': 'Three strategies, one workload &mdash; cost and task pass rate',
        'ko': '세 전략, 하나의 워크로드 &mdash; 비용과 과제 통과율',
    },
    'k099': {
        'en': 'Each single-tier strategy either costs more or solves fewer tasks. Cheapest-first escalation keeps a 100% task pass rate at less than premium-on-every-task cost.',
        'ko': '단일 티어 전략은 비용이 더 들거나 푸는 태스크가 적다. 싼 모델을 먼저 시도하고 실패를 확인한 뒤 상위 모델을 다시 호출하는 방식은 모든 과제에 프리미엄을 쓸 때보다 낮은 비용으로 과제 통과율 100%를 유지한다.',
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
        'en': 'pass rate &mdash;',
        'ko': '통과율 &mdash;',
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
        'en': 'pass rate &mdash;',
        'ko': '통과율 &mdash;',
    },
    'k107': {
        'en': 'holds the pass rate &mdash; but the most expensive',
        'ko': '통과율은 유지 &mdash; 하지만 가장 비싸다',
    },
    'k108': {
        'en': 'cheapest-first escalation',
        'ko': '싼 모델 먼저 올리는 방식',
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
        'en': 'pass rate &mdash;',
        'ko': '통과율 &mdash;',
    },
    'k112': {
        'en': 'every task passes, at less than premium cost',
        'ko': '프리미엄보다 낮은 비용으로 모든 과제 통과',
    },
    'k113': {
        'en': 'Cost &times; task pass rate &mdash; what each strategy costs and how many tasks it solves',
        'ko': '비용 &times; 과제 통과율 &mdash; 각 전략이 얼마를 쓰고 몇 과제를 푸는지',
    },
    'k114': {
        'en': 'run a replay&#8230;',
        'ko': '재생 실행&#8230;',
    },
    'k115': {
        'en': 'single-call',
        'ko': 'single-call',
    },
    'k116': {
        'en': ' (blue dot) = a strategy that picks a model ',
        'ko': ' (파란 점) = 프롬프트마다\n        모델을 ',
    },
    'k117': {
        'en': 'once',
        'ko': '한 번',
    },
    'k118': {
        'en': ' per prompt and stops. Because it never escalates after a failed result, its task pass rate stays low on this synthetic workload. By contrast, ',
        'ko': ' 고르고 멈추는 단일 호출 방식입니다. 실패한 뒤 상위 모델로 옮기지 않아 이 합성 워크로드에서 과제 통과율이 낮습니다. 반면 ',
    },
    'k119': {
        'en': 'observe-then-escalate routing',
        'ko': '실패를 확인한 뒤 상위 모델을 다시 호출하는 방식',
    },
    'k120': {
        'en': ' reaches a 100% task pass rate at a comparable projected cost. ',
        'ko': '은 비슷한 투영 비용으로 과제 통과율 100%에 도달합니다.\n        ',
    },
    'k121': {
        'en': 'Offline experiment 07 &rarr;',
        'ko': '오프라인 실험 07 &rarr;',
    },
    'k122': {
        'en': 'measured=false',
        'ko': 'measured=false',
    },
    'k123': {
        'en': 'Run a replay to compare all-mini, all-premium and cheapest-first escalation. All-mini costs less but solves fewer tasks. All-premium solves them but costs the most. Only escalation keeps a 100% task pass rate below all-premium cost.',
        'ko': '재생으로 all-mini, all-premium, 싼 모델 먼저 올리는 방식을 비교합니다. all-mini는 비용이 낮지만 푸는 과제가 적고, all-premium은 과제를 풀지만 비용이 가장 높습니다. 싼 모델 먼저 올리는 방식만이 all-premium보다 낮은 비용으로 과제 통과율 100%를 지킵니다.',
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
        'en': 'Click each experiment for cost &middot; task pass rate &middot;',
        'ko': '각 실험을 눌러 비용 &middot; 과제 통과율 &middot; ',
    },
    'k127': {
        'en': 'extra cost of calling every candidate',
        'ko': '추가 후보 호출 비용',
    },
    'k128': {
        'en': '&middot; reproduction check. The numbers are offline metrics in the Azure AI Foundry shape (labels.measured=false).',
        'ko': ' &middot; 재현 검사를\n      확인하세요. 수치는 Azure AI Foundry 형태의 오프라인 메트릭입니다 (labels.measured=false).',
    },
    'k129': {
        'en': 'loading experiments&#8230;',
        'ko': '실험 로딩&#8230;',
    },
    'k130': {
        'en': 'run history',
        'ko': '실행 이력',
    },
    'k131': {
        'en': 'Recorded run history',
        'ko': '기록된 실험 실행 이력',
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
        'en': 'pass rate',
        'ko': '통과율',
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
        'en': 'extra candidate-call cost',
        'ko': '추가 후보 호출 비용',
    },
    'k139': {
        'en': 'ratio',
        'ko': '배수',
    },
    'k140': {
        'en': 'reproduction',
        'ko': '재현',
    },
    'k141': {
        'en': 'loading history&#8230;',
        'ko': '이력 로딩&#8230;',
    },
    'k142': {
        'en': 'Removing the expensive last-resort models drops the task pass rate',
        'ko': '실패 뒤 재시도할 비싼 모델을 빼면 과제 통과율이 낮아진다',
    },
    'k143': {
        'en': 'A different policy, same workload. Deleting the expensive last-resort models (',
        'ko': '다른 정책, 같은 워크로드. 실패 뒤 재시도할 비싼 모델(',
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
        'en': 'keeps the expensive last resort',
        'ko': '실패 뒤 재시도할 비싼 모델을 유지',
    },
    'k149': {
        'en': 'routed &mdash;',
        'ko': '라우팅 &mdash;',
    },
    'k150': {
        'en': 'every task passes &mdash; the last-resort model catches the hard ones',
        'ko': '모든 과제 통과 &mdash; 재시도할 상위 모델이 어려운 과제를 잡아낸다',
    },
    'k151': {
        'en': 'cost-cut',
        'ko': 'cost-cut',
    },
    'k152': {
        'en': 'deletes the expensive last resort',
        'ko': '실패 뒤 재시도할 비싼 모델을 지운다',
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
        'en': "Cost-cut's routed bill is lower only because it stopped covering hard tasks &mdash; that is dropped work, not savings. Cost is comparable only at a fixed task pass rate.",
        'ko': 'cost-cut의 라우팅 청구액이 낮은 건 어려운 과제 커버를 멈췄기 때문일 뿐 &mdash; 그건 절감이 아니라 버려진 작업이다. 비용은 과제 통과율을 고정했을 때만 비교 가능하다.',
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
        'en': 'Offline experiment 03 &middot; task pass rate after removing the last-resort models',
        'ko': '오프라인 실험 03 &middot; 실패 뒤 재시도할 모델을 뺀 뒤의 과제 통과율',
    },
    'k160': {
        'en': 'Fan-out setting &mdash; how often the router calls every candidate',
        'ko': '팬아웃 설정 &mdash; 라우터가 모든 후보를 얼마나 자주 부를지',
    },
    'k161': {
        'en': "Same ensemble workload, one setting: the budget gate's ",
        'ko': '같은 앙상블 워크로드에서 예산 게이트의 설정 하나를 바꿉니다:',
    },
    'k162': {
        'en': 'compare_min_value',
        'ko': 'compare_min_value',
    },
    'k163': {
        'en': '. Raise it and the router calls every candidate on fewer tasks. The task pass rate and the savings stay unchanged while the extra candidate calls cost less. Offline experiment 05 (fan out on every task) vs 06 (fan out on none).',
        'ko': '. 이 값을 올리면 모든 후보를 부르는 과제가 줄어듭니다. 과제 통과율과 절감은 그대로이고 추가 후보 호출 비용만 낮아집니다. 오프라인 실험 05(모든 과제 팬아웃) vs 06(전혀 팬아웃 안 함).',
    },
    'k164': {
        'en': '&#9646; extra candidate-call cost',
        'ko': '&#9646; 추가 후보 호출 비용',
    },
    'k165': {
        'en': ' (falls)',
        'ko': '(낮아짐)',
    },
    'k166': {
        'en': '&ndash;&ndash; task pass rate',
        'ko': '&ndash;&ndash; 과제 통과율',
    },
    'k167': {
        'en': ' (unchanged)',
        'ko': '(변화 없음)',
    },
    'k168': {
        'en': '&ndash;&ndash; savings vs premium on every task',
        'ko': '&ndash;&ndash; 모든 과제 프리미엄 대비 절감',
    },
    'k169': {
        'en': ' (unchanged)',
        'ko': '(변화 없음)',
    },
    'k170': {
        'en': 'fan-out (compare)',
        'ko': '팬아웃(compare)',
    },
    'k171': {
        'en': 'pass rate',
        'ko': '통과율',
    },
    'k172': {
        'en': 'savings',
        'ko': '절감',
    },
    'k173': {
        'en': 'extra candidate-call cost',
        'ko': '추가 후보 호출 비용',
    },
    'k174': {
        'en': 'fan-out $',
        'ko': '팬아웃 $',
    },
    'k175': {
        'en': 'extra candidate-call cost &times;',
        'ko': '추가 후보 호출 비용 &times;',
    },
    'k176': {
        'en': 'On this deterministic projection, calling every candidate finds the same cheapest-passing winner that ordered escalation already reaches. The extra calls do not change the winner. Turn fan-out down to zero and keep every win. (Best-of-N can lift quality in a real system; this projection does not model that, so measure the lift before paying.)',
        'ko': "이 결정론적 투영에서 모든 후보를 불러도 ordered 에스컬레이션이 이미 도달하는 것과 같은 '통과하는 가장 싼' 승자를 찾습니다. 추가 호출은 승자를 바꾸지 않습니다. 팬아웃을 0으로 내리고 모든 통과를 유지합니다. (실제 시스템에서 best-of-N은 품질을 끌어올릴 수 있습니다. 이 투영은 그 효과를 모델링하지 않으므로 비용을 내기 전에 향상을 측정해야 합니다.)",
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
        'en': 'Offline experiment 06 &middot; the fan-out setting turned off',
        'ko': '오프라인 실험 06 &middot; 팬아웃 설정을 끈 실험',
    },
    'k181': {
        'en': 'At a glance',
        'ko': '한눈에',
    },
    'k182': {
        'en': 'Headline numbers for this replay &mdash; an offline projection over synthetic data.',
        'ko': '이번 재생의 헤드라인 수치 &mdash; 합성 데이터에 대한 오프라인 투영.',
    },
    'k183': {
        'en': 'tasks',
        'ko': '과제',
    },
    'k184': {
        'en': 'task pass rate',
        'ko': '과제 통과율',
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
        'en': 'Cost by task class &mdash; routed vs premium on every task',
        'ko': '작업 클래스별 비용 &mdash; 라우팅 vs 모든 과제 프리미엄',
    },
    'k195': {
        'en': 'run a replay&#8230;',
        'ko': '재생 실행&#8230;',
    },
    'k196': {
        'en': 'Model usage &mdash; tasks &amp; routed cost',
        'ko': '모델 사용 &mdash; 과제 &amp; 라우팅 비용',
    },
    'k197': {
        'en': 'run a replay&#8230;',
        'ko': '재생 실행&#8230;',
    },
    'k198': {
        'en': 'Routing mode',
        'ko': '라우팅 모드',
    },
    'k199': {
        'en': 'run a replay&#8230;',
        'ko': '재생 실행&#8230;',
    },
    'k200': {
        'en': 'Reason',
        'ko': '이유',
    },
    'k201': {
        'en': 'run a replay&#8230;',
        'ko': '재생 실행&#8230;',
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
        'en': 'Generic placeholder tiers &mdash; not real product names. They stand in for a\n        lightweight/high-volume model, an efficient coder, a balanced general model, a deliberate\n        reasoner, and a premium model.',
        'ko': '일반 placeholder 티어 &mdash; 실제 제품명이 아니다. 경량/대용량 모델, 효율적인 코더, 균형 잡힌 범용 모델, 신중한 추론기, 프리미엄 모델을 대신한다.',
    },
    'k239': {
        'en': 'Numbers are an offline projection over synthetic data &mdash; not measured. Model names are generic placeholders.',
        'ko': '수치는 합성 데이터에 대한 오프라인 투영이다 &mdash; 실측이 아니다. 모델명은 일반 placeholder다.',
    },
}

MEASURED = {
    'en': {
        'tabOffline': 'Offline replay',
        'tabMeasured': 'Measured run · experiment 12',
        'badgeOff': 'offline projection · labels.measured=false',
        'badgeMeas': 'sealed 03D snapshot · labels.measured=true',
        'eyebrow': 'Experiment 12 · measured run · sealed 03D snapshot',
        'title': 'Which backend the Model Router actually picked — one measured run on 24 coding tasks',
        'armKey': 'Arm labels — an arm is one comparison strategy: <span class="mono">router-cost</span> (Model Router in Cost mode) · <span class="mono">router-balanced</span> (Model Router in Balanced mode) · <span class="mono">router-quality</span> (Model Router in Quality mode) · <span class="mono">direct-premium</span> (calling the premium model directly · <span class="mono">gpt-5.6-sol</span>, the baseline all three router arms are compared against).',
        'sub': 'The same 24 coding tasks ran through four arms (three Model Router modes plus the direct-premium baseline) at n=3 on real Azure AI Foundry — experiment 12, the publishable second router-mode run. The result contains 288 cells and replayed byte-identically from a sealed snapshot. This read-only view uses the masked published.json bundle: aggregates only, no prompts, endpoints, or tenant ids. It is one measurement on one tenant, so read it as directional evidence, not a general result.',
        'lblCoverage': 'grading coverage',
        'lblUnpriced': 'unpriced',
        'lblReplay': 'replay verified',
        'lblSpend': 'spend',
        'armsTitle': 'Four arms — cost · pass rate · $/pass · grading coverage',
        'armsNote': 'The deployment appears under each arm. Every arm is cost_complete=true (unpriced 0%), and every cell uses pinned rates. Router-arm cost is composite: the Model Router input markup plus the resolved backend rates, not a synthetic bill. Pass rate counts tasks solved over tasks planned. Grading coverage counts cells graded over cells planned. The two denominators are different, so the two percentages are not comparable.',
        'cCost': 'cost',
        'cPass': 'pass rate',
        'cPerPass': '$/pass',
        'cCov': 'grading coverage',
        'cells': 'cells',
        'head': '<b>router-cost</b> keeps a <b>{qCost}</b> task pass rate while costing <b>{cheaper}% less</b> than direct-premium on this workload. The pass-rate gap is within <b>{gap} percentage points</b>. The timeout section below shows that the gap comes from timeouts, not code quality.',
        'domH': 'Quality mode cost more and passed less than direct-premium',
        'domP': "<b>router-quality</b> ({qCostUsd}) costs more than <b>direct-premium</b> ({premUsd}) and has a lower pass rate ({qQual} &lt; {premQual}). Quality mode reaches expensive models and adds the router input markup; calling direct-premium directly avoids that markup. On this workload, the direct call is cheaper and more accurate. Meanwhile router-cost keeps the same {costQual} pass rate at under 1/20 the cost.",
        'setupTitle': 'Setup — what was actually run',
        'setupNote': 'These are the real deployment and backend identifiers from the sealed run. Every name below comes verbatim from the masked bundle. The offline tab keeps synthetic placeholder model names because attaching real names to synthetic data would imply a per-model performance claim.',
        'setArms': 'Arms',
        'setBackends': 'Backends the router picked',
        'setWorkload': 'Workload',
        'setRun': 'Run conditions',
        'rosterEvidence': 'None of these is a deployment in this run — the four deployments are <span class="mono">{deps}</span>. The router selected these backends from its own managed roster; <b>grok-4-1-fast-reasoning</b> in particular was never deployed to this account, yet Cost mode routed 100% to it.',
        'workloadVal': 'curated-24 · {tasks} tasks × {arms} arms × n={n} = {cells} cells',
        'runVal': 'keyless Entra · sequential dispatch in a deterministic order (task-major → repeat → arm) · max_output_tokens is the only request parameter from the plan; sampling temperature is the service default',
        'backTitle': 'Backend distribution — which model each arm actually reached',
        'backNote': 'This distribution includes graded cells only; timeout cells whose backend never settled are excluded. Cost mode sent 100% to grok-4-1-fast-reasoning in both measured runs (experiment 11, voided by the grading-coverage gate, and this publishable run). Quality mode sent no cells to Grok at all. Two runs agreeing is a repeat, not a routing guarantee.',
        'toTitle': '11 timeout cells — shown, not hidden',
        'toNote': "All 11 are HTTP 408 read timeouts in the router arms; direct-premium had 0. Each timeout is excluded from grading coverage and counted as a failure in the pass rate. Those timeouts account for the entire pass-rate difference between the router arms and direct-premium. The 4.17 percentage point gap comes from latency (router backends p50 ~12–16s vs direct-premium ~4.2s), not code quality.",
        'toByArm': 'By arm',
        'toByTask': 'By task',
        'toArm': 'arm',
        'toTask': 'task',
        'toN': 'timeouts',
        'limTitle': 'Limits — read before generalizing',
        'limits': [
            '<b>24 tasks, so evidence_tier is directional.</b> A directional signal, not statistical confidence — a statistical conclusion would need ~100 problems.',
            '<b>Single tenant · single region · one measurement.</b> Replay guarantees reproduction of this run, not a population estimate.',
            '<b>Timeouts count against the router arms only.</b> The router backends have longer latency and hit the fixed timeout; direct-premium does not — a latency-profile difference, not code quality.',
            '<b>Router cost is composite.</b> The router input markup plus the resolved backend rates. It is not a synthetic bill, and it is not a rate you can quote for another tenant.',
            '<b>Do not generalize to other workloads.</b> Limited to this workload · this tenant · this one measurement.',
        ],
        'caveat': 'Sealed snapshot, rendered read-only — changing any number here would break the replay guarantee. Full write-up:',
        'caveatLink': 'Measured results',
        'armLbl': {
            'router-cost': 'Cost mode',
            'router-balanced': 'Balanced mode',
            'direct-premium': 'Direct premium',
            'router-quality': 'Quality mode',
        },
    },
    'ko': {
        'tabOffline': '오프라인 재생',
        'tabMeasured': '실측 실행 · 실험 12',
        'badgeOff': 'offline projection · labels.measured=false',
        'badgeMeas': 'sealed 03D 스냅샷 · labels.measured=true',
        'eyebrow': '실험 12 · 실측 실행 · 봉인된 03D 스냅샷',
        'title': 'Model Router가 실제로 고른 백엔드 — 코딩 과제 24개, 실측 1회',
        'armKey': '실험 arm 라벨 — arm은 비교에 쓰인 전략 하나를 뜻한다: <span class="mono">router-cost</span>(Model Router의 Cost 모드) · <span class="mono">router-balanced</span>(Model Router의 Balanced 모드) · <span class="mono">router-quality</span>(Model Router의 Quality 모드) · <span class="mono">direct-premium</span>(프리미엄 모델 직접 호출 · <span class="mono">gpt-5.6-sol</span>, 라우터 세 arm이 모두 이 기준선과 비교된다).',
        'sub': '같은 24개 코딩 과제를 실제 Azure AI Foundry에서 네 arm(Model Router 3모드 + direct-premium 기준선)으로 n=3씩 실행했다 — 라우터 모드 비교의 두 번째이자 발행 가능한 실행, 실험 12다. 결과는 288셀이며 봉인 스냅샷 재생에서 바이트 단위로 같았다. 이 읽기 전용 화면은 마스킹된 published.json 번들의 집계만 사용하며 프롬프트·엔드포인트·테넌트 식별자는 담지 않는다. 테넌트 하나에서 한 번 잰 값이므로 일반 결론이 아니라 방향성 근거로 읽어야 한다.',
        'lblCoverage': '채점 커버리지',
        'lblUnpriced': 'unpriced',
        'lblReplay': '재생 검증됨',
        'lblSpend': 'spend',
        'armsTitle': '네 arm — 비용 · 통과율 · $/pass · 채점 커버리지',
        'armsNote': 'arm 이름 아래에 배포명을 적었다. 모든 arm이 cost_complete=true(unpriced 0%)이고 모든 셀에 고정 요율을 적용했다. 라우터 arm의 비용은 합성 청구액이 아니라 Model Router 입력 마크업과 해석된 백엔드 요율을 합친 복합 요율이다. 통과율은 해결한 과제 수를 계획된 과제 수로, 채점 커버리지는 채점된 셀 수를 계획된 셀 수로 나눈 값이다. 분모가 다르므로 두 백분율을 같은 지표로 비교하면 안 된다.',
        'cCost': '비용',
        'cPass': '통과율',
        'cPerPass': '$/pass',
        'cCov': '채점 커버리지',
        'cells': '셀',
        'head': '<b>router-cost</b>는 이 워크로드에서 통과율 <b>{qCost}</b>를 유지하면서 direct-premium보다 비용이 <b>{cheaper}% 낮다</b>. 통과율 차이는 <b>{gap}퍼센트포인트</b> 이내다. 아래 타임아웃 절에 따르면 이 차이는 코드 품질이 아니라 타임아웃에서 나왔다.',
        'domH': 'Quality 모드는 direct-premium보다 비용이 높고 통과율이 낮았다',
        'domP': '<b>router-quality</b>({qCostUsd})는 <b>direct-premium</b>({premUsd})보다 비용이 높고 통과율은 낮다({qQual} &lt; {premQual}). Quality 모드는 비싼 모델에 도달하면서 라우터 입력 마크업이 붙지만 direct-premium을 직접 부르면 그 마크업이 없다. 이 워크로드에서는 직접 호출이 더 싸고 정확하다. 한편 router-cost는 같은 {costQual} 통과율을 1/20 미만 비용으로 유지한다.',
        'setupTitle': '실험 구성 — 무엇을 돌렸나',
        'setupNote': '봉인된 실행의 실제 배포·백엔드 식별자다. 아래 이름은 모두 마스킹된 번들에서 그대로 가져왔다. 합성 데이터에 실제 모델명을 붙이면 모델별 성능 주장처럼 보이므로 offline 탭은 합성 placeholder 모델명을 유지한다.',
        'setArms': 'Arm 구성',
        'setBackends': '라우터가 고른 백엔드',
        'setWorkload': '워크로드',
        'setRun': '실행 조건',
        'rosterEvidence': '이 중 어느 것도 이번 실행의 배포가 아니다 — 배포는 넷뿐이다: <span class="mono">{deps}</span>. 라우터는 이 백엔드들을 자기 관리 로스터에서 골랐다; 특히 <b>grok-4-1-fast-reasoning</b>은 이 계정에 배포된 적이 없는데도 Cost 모드가 100%를 그리로 보냈다.',
        'workloadVal': 'curated-24 · 과제 {tasks}개 × arm {arms}개 × n={n} = {cells}셀',
        'runVal': 'keyless Entra · 디스패치 순서가 고정된 순차 실행(과제 → 반복 → arm) · 계획에서 받아 요청에 싣는 값은 max_output_tokens 하나이고 샘플링 온도는 서비스 기본값이다',
        'backTitle': '백엔드 분포 — 각 arm이 실제로 도달한 모델',
        'backNote': '채점된 셀만 포함하며 백엔드가 확정되지 않은 타임아웃 셀은 제외한다. Cost 모드는 두 실측 실행(채점 커버리지 게이트로 무효 처리된 실험 11과 이 발행 실행) 모두 100%를 grok-4-1-fast-reasoning으로 보냈다. Quality 모드는 Grok으로 보낸 셀이 없다. 두 실행이 일치한 것은 반복 관측이지 라우팅 보장이 아니다.',
        'toTitle': '타임아웃 11셀 — 숨기지 않고 보여준다',
        'toNote': '11셀 모두 라우터 arm에서 난 HTTP 408 읽기 타임아웃이며 direct-premium은 0이다. 각 타임아웃은 채점 커버리지에서 제외하고 통과율에서는 실패로 집계한다. 이 타임아웃들이 라우터 arm과 direct-premium 사이의 통과율 차이 전부를 만든다. 4.17퍼센트포인트 격차는 지연 차이(라우터 백엔드 p50 ~12–16초 vs direct-premium ~4.2초)이지 코드 품질이 아니다.',
        'toByArm': 'arm별',
        'toByTask': '과제별',
        'toArm': 'arm',
        'toTask': '과제',
        'toN': '타임아웃',
        'limTitle': '한계 — 일반화 전에 읽어라',
        'limits': [
            '<b>과제 24개라 evidence_tier는 directional이다.</b> 통계적 신뢰가 아니라 방향성 신호다 — 통계적 결론에는 ~100문제가 필요하다.',
            '<b>단일 테넌트 · 단일 리전 · 1회 측정.</b> 재생은 이 실행의 재현을 보장하지 모집단 추정을 보장하지 않는다.',
            '<b>타임아웃은 라우터 arm에만 불리하게 집계된다.</b> 라우터 백엔드는 지연이 더 길어 고정 타임아웃에 걸리고 direct-premium은 걸리지 않는다 — 지연 프로파일 차이지 코드 품질이 아니다.',
            '<b>라우터 비용은 복합 요율이다.</b> 라우터 입력 마크업과 해석된 백엔드 요율의 합이다. 합성 청구액이 아니며, 다른 테넌트에 그대로 인용할 수 있는 요율도 아니다.',
            '<b>다른 워크로드로 일반화하지 마라.</b> 이 워크로드 · 이 테넌트 · 이 1회 측정에 한정된다.',
        ],
        'caveat': '봉인 스냅샷을 읽기 전용으로 렌더한 것 — 여기 숫자를 바꾸면 재생 보장이 깨진다. 전체 서술:',
        'caveatLink': '실측 결과',
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
            'en': 'Experiment 06 · turn unnecessary fan-out down to zero and keep the savings',
            'ko': '실험 06 · 필요 없는 팬아웃을 0으로 줄이고 절감은 유지하기',
        },
        'summary': {
            'en': "Reuses experiment 05's workload unchanged but turns fan-out off by raising the budget gate's compare_min_value above every task's value. The task pass rate stays at 100% and savings hold at ~47% against premium on every task, while the extra candidate-call cost falls to ~$0.00. On this deterministic offline projection, fan-out picks the same cheapest-passing model that ordered escalation already finds. Turning it off removes the extra calls with no loss.",
            'ko': '실험 05와 같은 워크로드를 그대로 쓰되 예산 게이트의 compare_min_value를 모든 태스크 가치보다 높여 팬아웃을 끕니다. 과제 통과율 100%와 모든 과제 프리미엄 대비 ~47% 절감은 그대로이고 추가 후보 호출 비용은 ~$0.00으로 낮아집니다. 이 결정론적 오프라인 투영에서 팬아웃은 ordered 에스컬레이션이 이미 찾는 가장 싼 통과 모델과 같은 승자를 고릅니다. 팬아웃을 끄면 결과 손실 없이 추가 호출만 없어집니다.',
        },
    },
    'curated': {
        'title': {
            'en': 'Experiment 02 · five tasks you can follow by eye',
            'ko': '실험 02 · 눈으로 따라가는 5개 태스크',
        },
        'summary': {
            'en': 'Routes a handful of tasks carrying hand-written offline signals — a minimal sample where you can read the data end to end and watch each routing decision by eye.',
            'ko': '손으로 작성한 오프라인 신호가 붙은 소수의 태스크를 라우팅해, 데이터를 처음부터 끝까지 읽으며 라우팅 결정을 눈으로 확인할 수 있는 최소 샘플입니다.',
        },
    },
    'ensemble': {
        'title': {
            'en': 'Experiment 05 · call every candidate and pay for every call',
            'ko': '실험 05 · 모든 후보를 부르고 모든 호출 비용 내기',
        },
        'summary': {
            'en': "Sends high-value tasks to every candidate (compare mode) and keeps the best result. Several models pass, so best-of-N keeps the cheapest passing model. Fan-out also runs every result it discards, so the run costs 3.7× as much as the winner alone. Routing uses fan-out only where the task value is high.",
            'ko': '가치가 높은 태스크를 모든 후보에 보내고(compare 모드) 가장 좋은 결과를 남깁니다. 여러 모델이 통과하므로 best-of-N은 가장 싼 통과 모델을 남깁니다. 팬아웃은 버릴 결과도 모두 실행하므로 승자 한 명만 부를 때보다 3.7배를 냅니다. 라우팅은 태스크 가치가 높은 곳에서만 팬아웃합니다.',
        },
    },
    'hero': {
        'title': {
            'en': 'Experiment 01 · same task pass rate, lower cost',
            'ko': '실험 01 · 같은 과제 통과율, 더 낮은 비용',
        },
        'summary': {
            'en': "Routes 100 synthetic tasks 'cheapest passing model first, escalate only on failure' and compares that against sending every task to the premium model.",
            'ko': "합성 워크로드 100건을 '통과하는 가장 싼 모델 먼저, 실패할 때만 상위 모델로' 라우팅하고, 모든 태스크를 프리미엄 모델로 보내는 방식과 비교합니다.",
        },
    },
    'limits': {
        'title': {
            'en': 'Experiment 04 · no free lunch — the limits of routing',
            'ko': '실험 04 · 공짜 점심은 없다 — 라우팅의 한계',
        },
        'summary': {
            'en': "A workload where every task is genuinely hard and only the most expensive model passes. Routing tries the cheap models first, but they all fail and it escalates to the top model, so savings are 0%. Routing does not invent savings that aren't there — it spends honestly on hard work.",
            'ko': '모든 태스크가 진짜 어려워 가장 비싼 모델만 통과하는 워크로드입니다. 라우팅은 싼 모델부터 시도하지만 전부 실패해 최상위 모델로 에스컬레이션하며, 절감은 0%. 라우팅은 없는 절감을 지어내지 않고, 어려운 일엔 정직하게 비용을 씁니다.',
        },
    },
    'single-call': {
        'title': {
            'en': 'Experiment 07 · pick one model up front vs observe-then-escalate',
            'ko': '실험 07 · 앞서 한 번 고르기 vs 관찰하고 올리기',
        },
        'summary': {
            'en': "Projects a 'single-call' strategy that picks one model per prompt up front (what the built-in Model Router already does well) as a difficulty-tiered one-shot arm, and compares its projected cost and task pass rate with this repo's 'observe and escalate only when needed' routing. The one-shot arm commits early and loses pass rate; observing the result and escalating only on failure recovers it in the same cost band. Both arms are offline projections over synthetic data, not a measurement of any product.",
            'ko': "프롬프트당 모델 하나를 앞서 고르는 '단일 호출' 방식(내장 Model Router가 이미 잘 하는 일)을 난이도 기반 원샷 arm으로 투영하고, 이 저장소의 '관찰하고 필요할 때만 올리는' 라우팅과 투영 비용·과제 통과율을 비교합니다. 원샷은 앞서 커밋해 통과율을 잃고, 결과를 보고 실패할 때만 올리는 방식이 같은 비용대에서 그 통과율을 되찾습니다. 두 arm 모두 합성 데이터에 대한 오프라인 투영이며 특정 제품을 측정한 값이 아닙니다.",
        },
    },
}


# ---------------------------------------------------------------------------
# Compare ("one problem, four strategies") payload — deterministic localization.
#
# ``router.arena`` builds this payload in English from structured facts (the
# approach, its models, the chosen model, pass/fail). Rather than translating the
# finished sentences, :func:`localize_compare` *rebuilds* label and detail from
# those same structured fields, so the English side is reproduced byte-for-byte
# and the Korean side cannot silently drift. Code identifiers — task ids, model
# names, function signatures, literals — are never translated.
# ---------------------------------------------------------------------------

# Authored synthetic problems (samples/prompts/curated-arena.sample.json). The
# English side must stay identical to the fixture; only the Korean is new.
ARENA_PROBLEMS: dict[str, dict[str, dict[str, str]]] = {
    't-0001': {
        'title': {
            'en': 'slugify(title)',
            'ko': 'slugify(title) 구현',
        },
        'prompt': {
            'en': 'Implement slugify(title: str) -> str: lowercase the text, strip surrounding whitespace, and collapse every run of non-alphanumeric characters into a single hyphen, leaving no leading or trailing hyphen. Example: "  Hello,  World! " -> "hello-world".',
            'ko': 'slugify(title: str) -> str를 구현하세요. 텍스트를 소문자로 바꾸고, 앞뒤 공백을 없애고, 영숫자가 아닌 문자가 이어지는 구간을 하이픈 하나로 합치되 맨 앞과 맨 뒤에는 하이픈이 남지 않아야 합니다. 예: "  Hello,  World! " -> "hello-world".',
        },
        'acceptance': {
            'en': 'Collapses repeated separators, trims edge hyphens, and returns an empty string for all-symbol input.',
            'ko': '구분자가 반복되면 하나로 합치고, 양끝 하이픈을 없애며, 기호만 있는 입력에는 빈 문자열을 돌려줍니다.',
        },
    },
    't-0003': {
        'title': {
            'en': 'Patch parse_duration to accept combined units',
            'ko': 'parse_duration이 복합 단위를 받도록 고치기',
        },
        'prompt': {
            'en': 'The repo\'s parse_duration(text: str) -> int helper returns None for combined values like "1h30m" or "2m30s". Patch it to sum consecutive <number><unit> segments (h/m/s) into total seconds, reject empty or malformed input, and keep the existing single-unit tests green.',
            'ko': '저장소의 parse_duration(text: str) -> int 헬퍼는 "1h30m"이나 "2m30s" 같은 복합 값에 None을 돌려줍니다. 연속된 <number><unit> 구간(h/m/s)을 초 단위로 합산하도록 고치고, 비어 있거나 형식이 잘못된 입력은 거부하며, 기존 단일 단위 테스트는 그대로 통과시키세요.',
        },
        'acceptance': {
            'en': '"1h30m" -> 5400, "45s" -> 45, "" and "10x" are rejected, and the existing single-unit tests still pass.',
            'ko': '"1h30m" -> 5400, "45s" -> 45이고, ""와 "10x"는 거부되며, 기존 단일 단위 테스트가 그대로 통과합니다.',
        },
    },
    't-0004': {
        'title': {
            'en': 'Plan cursor pagination for GET /orders',
            'ko': 'GET /orders에 커서 페이지네이션 설계하기',
        },
        'prompt': {
            'en': 'Draft a short implementation plan to add cursor-based pagination to the GET /orders endpoint: the request/response shape, what the opaque cursor encodes, the index/query changes, and how paging stays stable under concurrent inserts.',
            'ko': 'GET /orders 엔드포인트에 커서 기반 페이지네이션을 추가하는 짧은 구현 계획을 쓰세요. 요청·응답 형태, 불투명 커서가 담는 값, 인덱스와 쿼리 변경, 그리고 동시 삽입이 일어나도 페이징이 흔들리지 않게 하는 방법을 담습니다.',
        },
        'acceptance': {
            'en': "Names the cursor's fields, the stable ordering key, and the forward/backward paging contract.",
            'ko': '커서에 담기는 필드, 정렬을 고정하는 키, 앞뒤 페이징 계약을 명시합니다.',
        },
    },
    't-0005': {
        'title': {
            'en': 'Review a retry-backoff change',
            'ko': '재시도 백오프 변경 리뷰하기',
        },
        'prompt': {
            'en': "Review a diff that changes an HTTP client's retry loop from a fixed delay to exponential backoff. Decide whether it correctly caps at max_attempts, applies jitter, and stops on non-retryable status codes, and flag anything missing.",
            'ko': 'HTTP 클라이언트의 재시도 루프를 고정 지연에서 지수 백오프로 바꾸는 diff를 리뷰하세요. max_attempts에서 제대로 멈추는지, 지터를 적용하는지, 재시도하면 안 되는 상태 코드에서 중단하는지 판단하고 빠진 것을 지적합니다.',
        },
        'acceptance': {
            'en': 'Judges the max-attempts boundary, the jitter, and the retryable/non-retryable split.',
            'ko': '최대 시도 횟수 경계, 지터, 재시도 가능·불가능 구분을 판단합니다.',
        },
    },
    't-0006': {
        'title': {
            'en': 'Unit tests for merge_intervals',
            'ko': 'merge_intervals 단위 테스트 작성하기',
        },
        'prompt': {
            'en': 'Write unit tests for merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]], which merges overlapping and adjacent closed intervals. Cover overlap, adjacency (touching endpoints), a fully contained interval, unsorted input, a single interval, and empty input.',
            'ko': '겹치거나 맞닿은 닫힌 구간을 병합하는 merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]의 단위 테스트를 작성하세요. 겹침, 맞닿음(끝점이 같은 경우), 완전히 포함된 구간, 정렬되지 않은 입력, 구간 하나, 빈 입력을 다룹니다.',
        },
        'acceptance': {
            'en': 'Includes empty, single, unsorted, adjacency, and nested-containment cases.',
            'ko': '빈 입력, 구간 하나, 정렬되지 않은 입력, 맞닿음, 포함 관계 경우를 포함합니다.',
        },
    },
}

# ``_teaches`` verdicts from router.arena.
ARENA_TEACHES: dict[str, dict[str, str]] = {
    'easy · cheapest already passes': {
        'en': 'easy · cheapest already passes',
        'ko': '쉬움 · 가장 싼 모델이 이미 통과',
    },
    'cheapest fails · escalation recovers': {
        'en': 'cheapest fails · escalation recovers',
        'ko': '가장 싼 모델 실패 · 에스컬레이션이 회복',
    },
    'mixed': {'en': 'mixed', 'ko': '혼합'},
}

# Task-class and difficulty values, shown as *labels* in the compare panel. The
# same raw values stay untranslated in the per-task routing trace, where they are
# read as identifiers and the legend spells them out.
ARENA_CLASSES: dict[str, dict[str, str]] = {
    'plan': {'en': 'plan', 'ko': '계획'},
    'generate': {'en': 'generate', 'ko': '생성'},
    'test': {'en': 'test', 'ko': '테스트'},
    'validate': {'en': 'validate', 'ko': '검증'},
    'repo_patch': {'en': 'repo_patch', 'ko': '저장소 패치'},
}
ARENA_DIFFICULTIES: dict[str, dict[str, str]] = {
    'easy': {'en': 'easy', 'ko': '쉬움'},
    'medium': {'en': 'medium', 'ko': '보통'},
    'hard': {'en': 'hard', 'ko': '어려움'},
    'unspecified': {'en': 'unspecified', 'ko': '미지정'},
}

ARENA_APPROACH_LABELS: dict[str, dict[str, str]] = {
    'cheapest': {'en': 'Cheapest model only', 'ko': '가장 싼 모델만'},
    'premium': {'en': 'Premium model only', 'ko': '프리미엄 모델만'},
    'ensemble': {'en': 'Every candidate (fan-out)', 'ko': '모든 후보 호출(팬아웃)'},
    'router': {
        'en': 'Cheapest-first, escalate on failure',
        'ko': '싼 모델 먼저, 실패하면 올리기',
    },
}

# Detail sentences, keyed by the structured case they describe. ``{model}``,
# ``{count}`` and ``{steps}`` are filled from the payload, never parsed out of
# prose. The English templates must reproduce router.arena verbatim.
ARENA_DETAILS: dict[str, dict[str, str]] = {
    'cheapest.pass': {
        'en': 'One call to the cheapest tier ({model}).',
        'ko': '가장 싼 티어({model})로 한 번 호출합니다.',
    },
    'cheapest.fail': {
        'en': 'One call to the cheapest tier ({model}). It does not pass the checks on this task.',
        'ko': '가장 싼 티어({model})로 한 번 호출합니다. 이 과제에서는 검사를 통과하지 못합니다.',
    },
    'premium': {
        'en': 'One call to the most expensive tier ({model}), with no attempt at a cheaper candidate first.',
        'ko': '가장 비싼 티어({model})로 한 번 호출하며, 더 싼 후보를 먼저 시도하지 않습니다.',
    },
    'ensemble': {
        'en': 'Calls all {count} candidates and keeps the best answer. It reaches the highest task pass rate but pays for every candidate, including the ones it discards \u2014 the extra candidate-call cost.',
        'ko': '후보 {count}개를 모두 호출하고 가장 좋은 답을 남깁니다. 과제 통과율은 가장 높지만 버리는 호출까지 후보 전부에 비용을 냅니다 \u2014 추가 후보 호출 비용입니다.',
    },
    'router.escalated': {
        'en': 'Tries the cheapest candidate first and escalates only after a failed check: {steps}. {model} passed, and only that call is billed.',
        'ko': '가장 싼 후보부터 시도하고 검사에 실패할 때만 올립니다: {steps}. {model}에서 통과했고 그 호출 하나만 청구됩니다.',
    },
    'router.first_try': {
        'en': 'Tries the cheapest candidate first and escalates only after a failed check: {steps}. The cheapest tier {model} passed on the first try.',
        'ko': '가장 싼 후보부터 시도하고 검사에 실패할 때만 올립니다: {steps}. 가장 싼 티어 {model}에서 첫 시도에 통과했습니다.',
    },
    'router.none': {
        'en': 'Tries the cheapest candidate first and escalates only after a failed check: {steps}. No candidate passed.',
        'ko': '가장 싼 후보부터 시도하고 검사에 실패할 때만 올립니다: {steps}. 통과한 후보가 없습니다.',
    },
}


def _detail_case(approach: dict) -> tuple[str, dict[str, object]]:
    """Return the ``ARENA_DETAILS`` key and fill-ins for one approach entry."""
    name = approach.get("approach")
    models = [str(m) for m in (approach.get("models") or [])]
    chosen = approach.get("chosen_model")
    passed = bool(approach.get("passed"))
    if name == "cheapest":
        return ("cheapest.pass" if passed else "cheapest.fail"), {"model": models[0] if models else "\u2014"}
    if name == "premium":
        return "premium", {"model": models[0] if models else "\u2014"}
    if name == "ensemble":
        return "ensemble", {"count": len(models)}
    if name == "router":
        steps = " \u2192 ".join(models) if models else "\u2014"
        if not passed:
            return "router.none", {"steps": steps}
        key = "router.escalated" if len(models) > 1 else "router.first_try"
        return key, {"steps": steps, "model": chosen or (models[-1] if models else "\u2014")}
    raise AssertionError(f"unknown arena approach {name!r}")


def _fill(template: str, values: dict) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def localize_compare(payload: object, locale: str) -> object:
    """Rewrite the ``/compare`` payload's reader-facing prose into ``locale``.

    Rebuilds every label and detail from the payload's own structured fields, so
    applying ``en`` reproduces what :mod:`router.arena` wrote and applying ``ko``
    cannot drift out of sync with it. Task ids, model names, candidate lists,
    numbers and every ``labels`` flag are left exactly as they are.

    Raises when a task has no authored translation or an approach falls outside
    the known cases, so a new problem or a reworded strategy fails the build
    instead of leaking English into ``/ko/demo/``.
    """
    if locale not in LOCALES:
        raise ValueError(f"unknown demo locale {locale!r} (expected en or ko)")
    if not isinstance(payload, dict):
        return payload

    def _label(table: dict, value: str, what: str) -> str:
        entry = table.get(value)
        if not entry:
            raise AssertionError(f"compare payload has an untranslated {what}: {value!r}")
        return entry[locale]

    for arena in (payload.get("arenas") or {}).values():
        if not isinstance(arena, dict):
            continue
        tid = str(arena.get("task_id") or "")
        arena["class"] = _label(ARENA_CLASSES, str(arena.get("class") or ""), "task class")
        arena["difficulty"] = _label(
            ARENA_DIFFICULTIES, str(arena.get("difficulty") or ""), "difficulty"
        )
        problem = arena.get("problem")
        if isinstance(problem, dict):
            fields = ARENA_PROBLEMS.get(tid)
            if not fields:
                raise AssertionError(f"compare payload has an untranslated problem: {tid!r}")
            for field in ("title", "prompt", "acceptance"):
                if problem.get(field):
                    problem[field] = fields[field][locale]
        for approach in arena.get("approaches") or []:
            if not isinstance(approach, dict):
                continue
            approach["label"] = _label(
                ARENA_APPROACH_LABELS, str(approach.get("approach") or ""), "approach"
            )
            key, values = _detail_case(approach)
            approach["detail"] = _fill(ARENA_DETAILS[key][locale], values)

    for entry in payload.get("tasks") or []:
        if not isinstance(entry, dict):
            continue
        tid = str(entry.get("task_id") or "")
        entry["class"] = _label(ARENA_CLASSES, str(entry.get("class") or ""), "task class")
        entry["difficulty"] = _label(
            ARENA_DIFFICULTIES, str(entry.get("difficulty") or ""), "difficulty"
        )
        if entry.get("title"):
            fields = ARENA_PROBLEMS.get(tid)
            if not fields:
                raise AssertionError(f"compare payload has an untranslated problem: {tid!r}")
            entry["title"] = fields["title"][locale]
        if entry.get("teaches"):
            entry["teaches"] = _label(ARENA_TEACHES, str(entry["teaches"]), "teaches verdict")
    return payload


# ---------------------------------------------------------------------------
# Prose the browser builds at render time from a payload (so it cannot live in
# ``DEMO_STRINGS``, which only covers the static template). Injected once per
# locale as ``window.__D_STR__``; ``{name}`` placeholders are filled by the same
# ``mfmt`` helper the measured tab uses.
#
# ``checkLabels`` maps an experiment contract's raw check key to a reader label.
# The payload keeps the raw key untouched — the dashboard shows it as code next
# to the label — so nothing that consumes ``/experiments`` has to change.
# ---------------------------------------------------------------------------
DYNAMIC = {
    'en': {
        'healthOk': '● healthy · offline',
        'healthBad': 'unhealthy',
        'healthErr': 'unreachable',
        'policyVer': 'policy v',
        'tasksSuffix': ' tasks',
        'clsSaved': '{pct} saved',
        'cliffRouted': 'routed {usd}',
        'setMeta': '— {n} deployments · {source}',
        'setRunFailed': 'the candidate-set run failed',
        'setRunBtn': 'Run selection (recorded)',
        'setPicked': 'router picked: {mix}',
        'clsFooter': 'routed {routed} · premium-on-every-task {base} · {n} tasks',
        'modelTasks': '{n} tasks · {usd}',
        'modeTasks': '{n} tasks',
        'swFanOut': '{n}/{total} fan out',
        'swThreshold': 'threshold {v}',
        'progRouting': 'routing…',
        'progRouted': 'routed {i}/{n}',
        'progDone': 'done · {n} tasks',
        'progError': 'error — could not load the replay',
        'covWarn': '⚠ task pass rate dropped — the lower bill came from tasks left unsolved, not from cheaper routing.',
        'covPill': 'pass rate ',
        'usageSplit': 'Cheap tiers carried the volume: <b>{cheap}</b> handled <b>{cheapN}</b> tasks, while the premium tier <b>{top}</b> handled only the <b>{topN}</b> hardest.',
        'takeaway': 'Cheapest-only is cheaper but drops the task pass rate to {mini} — the cheap tier fails the hard tasks. Premium-only holds a {prem} pass rate but costs the most. Cheapest-first escalation is the only strategy that keeps a {mix} pass rate below all-premium cost.',
        'frontierAxis': 'task pass rate',
        'frontierAria': 'cost versus task pass rate, offline projection over synthetic data: only cheapest-first escalation reaches a 100% pass rate at low cost',
        'frontierMix': 'cheapest-first escalation',
        'cliffDrop': 'task pass rate −{pts} percentage points',
        'cliffTake': "Cost-cut's routed bill ({cand}) is lower than seed ({seed}) — but only because it stopped covering {pts} percentage points of the tasks. That is dropped work, not savings. Cost is comparable only at a fixed task pass rate.",
        'sweepAria': 'fan-out setting: the extra candidate-call cost collapses to zero while the task pass rate and the savings stay flat',
        'sweepDrop': 'extra candidate calls {from} → {to}',
        'heroSub': 'vs premium on every task — cheap-first routing; only {topN} of {tasks} tasks needed the top {top} tier, held at {cov} task pass rate · saved {saved}.',
        'journeyVerdict': 'Reproduction passed',
        'journeyMeta': '{tasks} tasks · replay verified · <code>measured=false</code>',
        'aUnitS': ' s',
        'aUnitMs': ' ms',
        'aModels': '{n} models',
        'aRowCost': 'cost',
        'aRowLatency': 'latency*',
        'aRowAccuracy': 'accuracy',
        'aPass': '✓ pass',
        'aFail': '✗ fail',
        'aWinCost': 'cheapest',
        'aWinLatency': 'fastest',
        'aAcceptance': 'Acceptance: ',
        'aSource': 'input: authored synthetic problem · offline projection · measured = false',
        'aVerdictEasy': 'On this {difficulty} task the <b>cheapest</b> model already passes — the router correctly just picks it, so the premium and every-candidate spend buys nothing extra. Routing earns its keep on the hard tasks, not this one.',
        'aVerdictRouter': 'Cheapest-first routing reaches a passing answer',
        'aVerdictRatio': ' at <b>{ratio}×</b> lower projected cost than calling the premium model directly',
        'aVerdictEnsemble': ' Calling every candidate also passes but pays for each one (<b>{usd}</b>), including the ones it discards.',
        'aVerdictLatency': ' No free lunch: on this illustrative latency projection cheapest-first is the <b>slowest</b> here because it escalates one call at a time — you trade latency for cost.',
        'aVerdictNone': 'No single-shot strategy passes cleanly on this task — weigh the cost, latency and accuracy trade-offs above.',
        'eKpiPass': 'task pass rate',
        'eKpiRouted': 'routed',
        'eKpiSaved': 'saved vs premium on every task',
        'eKpiTasks': 'tasks',
        'eKpiFanout': 'fan-out tasks',
        'eRepro': 'reproducible ✓',
        'eReproFail': 'reproduction FAILED',
        'eFanout': '🔀 <b>extra candidate-call cost</b>: this run called every candidate on <b>{n}</b> task(s), spending <b>{spend}</b> to run all of them but keeping only <b>{winners}</b> worth of winners — an extra <b>{extra}</b> ({ratio}×) for the calls it discarded.',
        'hPass': 'PASS',
        'hFail': 'FAIL',
        'hEmpty': 'no recorded runs yet',
        'checkLabels': {
            'coverage': 'task pass rate',
            'savings': 'savings vs premium on every task',
            'tasks': 'tasks',
            'fanout_tax_ceiling': 'extra candidate-call cost limit',
            'savings_ceiling': 'savings ceiling',
            'escalation_gain': 'pass-rate gain from escalation',
        },
        'checkTerms': [['tax ', 'extra candidate calls ']],
    },
    'ko': {
        'healthOk': '● 정상 · 오프라인',
        'healthBad': '비정상',
        'healthErr': '연결 안 됨',
        'policyVer': '정책 v',
        'tasksSuffix': '개 과제',
        'clsSaved': '{pct} 절감',
        'cliffRouted': '라우팅 {usd}',
        'setMeta': '— 배포 {n}개 · {source}',
        'setRunFailed': '후보 모델 세트 실행에 실패했습니다',
        'setRunBtn': '선택 실행(기록됨)',
        'setPicked': '라우터가 고른 모델: {mix}',
        'clsFooter': '라우팅 {routed} · 모든 과제 프리미엄 {base} · 과제 {n}개',
        'modelTasks': '과제 {n}개 · {usd}',
        'modeTasks': '과제 {n}개',
        'swFanOut': '{total}개 중 {n}개 팬아웃',
        'swThreshold': '임계값 {v}',
        'progRouting': '라우팅 중…',
        'progRouted': '라우팅 {i}/{n}',
        'progDone': '완료 · 과제 {n}개',
        'progError': '오류 — 재생을 불러오지 못했습니다',
        'covWarn': '⚠ 과제 통과율이 낮아졌습니다 — 청구액이 줄어든 건 라우팅이 싸서가 아니라 풀지 못한 과제가 생겼기 때문입니다.',
        'covPill': '통과율 ',
        'usageSplit': '물량은 싼 티어가 받았습니다: <b>{cheap}</b>가 <b>{cheapN}</b>개 과제를 처리했고, 프리미엄 티어 <b>{top}</b>는 가장 어려운 <b>{topN}</b>개만 맡았습니다.',
        'takeaway': '가장 싼 모델만 쓰면 비용은 낮지만 과제 통과율이 {mini}로 떨어집니다 — 싼 티어가 어려운 과제를 실패하기 때문입니다. 프리미엄만 쓰면 통과율 {prem}를 지키지만 비용이 가장 큽니다. 싼 모델 먼저 올리는 방식만이 all-premium보다 낮은 비용으로 통과율 {mix}를 유지합니다.',
        'frontierAxis': '과제 통과율',
        'frontierAria': '비용 대 과제 통과율, 합성 데이터에 대한 오프라인 투영: 낮은 비용으로 통과율 100%에 도달하는 것은 싼 모델 먼저 올리는 방식뿐입니다',
        'frontierMix': '싼 모델 먼저 올리는 방식',
        'cliffDrop': '과제 통과율 −{pts}퍼센트포인트',
        'cliffTake': 'cost-cut의 라우팅 청구액({cand})이 seed({seed})보다 낮은 건 과제의 {pts}퍼센트포인트를 더 이상 커버하지 않기 때문입니다. 그건 절감이 아니라 버려진 작업입니다. 비용은 과제 통과율을 고정했을 때만 비교할 수 있습니다.',
        'sweepAria': '팬아웃 설정: 추가 후보 호출 비용은 0으로 내려가고 과제 통과율과 절감은 그대로입니다',
        'sweepDrop': '추가 후보 호출 비용 {from} → {to}',
        'heroSub': '모든 과제 프리미엄 대비 — 싼 모델 먼저 라우팅. 과제 {tasks}개 중 {topN}개만 최상위 {top} 티어가 필요했고, 과제 통과율 {cov}를 유지하며 {saved}를 절감했습니다.',
        'journeyVerdict': '재현 통과',
        'journeyMeta': '과제 {tasks}개 · 재생 검증됨 · <code>measured=false</code>',
        'aUnitS': '초',
        'aUnitMs': 'ms',
        'aModels': '모델 {n}개',
        'aRowCost': '비용',
        'aRowLatency': '지연*',
        'aRowAccuracy': '정확도',
        'aPass': '✓ 통과',
        'aFail': '✗ 실패',
        'aWinCost': '가장 저렴',
        'aWinLatency': '가장 빠름',
        'aAcceptance': '통과 기준: ',
        'aSource': '입력: 작성된 합성 문제 · 오프라인 투영 · measured = false',
        'aVerdictEasy': '난이도 {difficulty}인 이 과제는 <b>가장 싼</b> 모델이 이미 통과합니다 — 라우터도 그 모델을 고르므로 프리미엄이나 모든 후보 호출에 쓴 비용은 아무것도 더 사주지 않습니다. 라우팅의 값어치는 어려운 과제에서 나오지 이런 과제에서 나오지 않습니다.',
        'aVerdictRouter': '싼 모델 먼저 라우팅이 통과하는 답에 도달합니다',
        'aVerdictRatio': '. 프리미엄 모델을 직접 부를 때보다 투영 비용이 <b>{ratio}배</b> 낮습니다',
        'aVerdictEnsemble': ' 모든 후보 호출도 통과하지만 버리는 것까지 후보마다 비용을 냅니다(<b>{usd}</b>).',
        'aVerdictLatency': ' 공짜는 없습니다: 이 예시용 지연 투영에서 싼 모델 먼저 라우팅이 <b>가장 느립니다</b>. 한 번에 한 호출씩 올리기 때문이며, 비용을 아끼는 대신 지연을 내주는 셈입니다.',
        'aVerdictNone': '이 과제에서는 한 번에 끝나는 전략 중 깔끔하게 통과하는 것이 없습니다 — 위의 비용·지연·정확도 트레이드오프를 견주어 보세요.',
        'eKpiPass': '과제 통과율',
        'eKpiRouted': '라우팅 비용',
        'eKpiSaved': '모든 과제 프리미엄 대비 절감',
        'eKpiTasks': '과제 수',
        'eKpiFanout': '팬아웃 과제',
        'eRepro': '재현 가능 ✓',
        'eReproFail': '재현 실패',
        'eFanout': '🔀 <b>추가 후보 호출 비용</b>: 이 실행은 과제 <b>{n}</b>건에서 모든 후보를 불렀고, 전부 실행하는 데 <b>{spend}</b>를 썼지만 남긴 승자는 <b>{winners}</b>어치입니다 — 버린 호출에 <b>{extra}</b>({ratio}배)를 더 냈습니다.',
        'hPass': '통과',
        'hFail': '실패',
        'hEmpty': '기록된 실행이 아직 없습니다',
        'checkLabels': {
            'coverage': '통과율',
            'savings': '모든 과제 프리미엄 대비 절감',
            'tasks': '과제 수',
            'fanout_tax_ceiling': '추가 후보 호출 비용 상한',
            'savings_ceiling': '절감 상한',
            'escalation_gain': '에스컬레이션으로 얻은 통과율',
        },
        'checkTerms': [
            ['tax ', '추가 후보 호출 비용 '],
            ['observe-then-escalate ', '에스컬레이션 '],
            ['percentage points', '퍼센트포인트'],
        ],
    },
}


def dynamic_payload(locale: str) -> dict:
    """Single-locale table for browser-built prose, injected as ``window.__D_STR__``."""
    if locale not in LOCALES:
        raise ValueError(f"unknown demo locale {locale!r} (expected en or ko)")
    return DYNAMIC[locale]


# ---------------------------------------------------------------------------
# Model-catalog prose from ``/policy``. The demo renders each tier's name, its
# reasoning level and its one-line role, so all three need a Korean side. Model
# ids are placeholder identifiers and stay as they are.
# ---------------------------------------------------------------------------
CATALOG_TIERS: dict[str, dict[str, str]] = {
    'Lightweight': {'en': 'Lightweight', 'ko': '경량'},
    'Efficient coder': {'en': 'Efficient coder', 'ko': '효율형 코더'},
    'Balanced': {'en': 'Balanced', 'ko': '균형형'},
    'Reasoning': {'en': 'Reasoning', 'ko': '추론형'},
    'Premium frontier': {'en': 'Premium frontier', 'ko': '프리미엄 최상위'},
}
CATALOG_REASONING: dict[str, dict[str, str]] = {
    'minimal': {'en': 'minimal', 'ko': '최소'},
    'light': {'en': 'light', 'ko': '가벼움'},
    'moderate': {'en': 'moderate', 'ko': '보통'},
    'high': {'en': 'high', 'ko': '높음'},
    'maximum': {'en': 'maximum', 'ko': '최대'},
}
CATALOG_ROLES: dict[str, dict[str, str]] = {
    'mini-fast': {
        'en': 'Cheapest, lowest-latency tier. Handles simple, high-volume work (short generation, quick validation) where deep reasoning is not needed.',
        'ko': '가장 싸고 지연이 가장 짧은 티어입니다. 깊은 추론이 필요 없는 단순·대량 작업(짧은 생성, 빠른 검증)을 맡습니다.',
    },
    'swift-coder': {
        'en': 'Low-cost, code-specialized tier. Good default for straightforward code generation and small edits before escalating to a pricier model.',
        'ko': '비용이 낮고 코드에 특화된 티어입니다. 더 비싼 모델로 올리기 전에 단순한 코드 생성과 작은 수정을 맡기기 좋은 기본값입니다.',
    },
    'balanced-pro': {
        'en': 'General-purpose mid tier. The everyday quality/cost trade-off used when the lightweight tier is not reliable enough.',
        'ko': '범용 중간 티어입니다. 경량 티어로는 충분히 미덥지 않을 때 쓰는 평상시 품질·비용 절충안입니다.',
    },
    'deep-reasoner': {
        'en': 'Higher-cost tier for deliberate, multi-step reasoning on hard planning or repository-patch tasks where correctness matters more than price.',
        'ko': '비용이 더 드는 티어로, 가격보다 정확성이 중요한 어려운 계획이나 저장소 패치 과제에서 여러 단계를 신중히 추론합니다.',
    },
    'premium-max': {
        'en': 'Maximum-capability ceiling and the most expensive tier. Reserved for the hardest tasks whose value clearly justifies the extra spend.',
        'ko': '성능 천장이자 가장 비싼 티어입니다. 추가 비용을 쓸 값어치가 분명한 가장 어려운 과제에만 배정합니다.',
    },
}


def localize_policy(payload: object, locale: str) -> object:
    """Translate the ``/policy`` catalog prose (tier, reasoning level, role).

    Model ids, class names, versions and every numeric prior are untouched. An
    unknown tier, level or model fails loudly so a catalog change cannot leak
    English into ``/ko/demo/``.
    """
    if locale not in LOCALES:
        raise ValueError(f"unknown demo locale {locale!r} (expected en or ko)")
    if not isinstance(payload, dict):
        return payload

    def _entry(entry: dict) -> None:
        model = str(entry.get("model") or "")
        for field, table, key in (
            ("tier", CATALOG_TIERS, str(entry.get("tier") or "")),
            ("reasoning", CATALOG_REASONING, str(entry.get("reasoning") or "")),
            ("role", CATALOG_ROLES, model),
        ):
            if not entry.get(field):
                continue
            pair = table.get(key)
            if not pair:
                raise AssertionError(
                    f"policy catalog has an untranslated {field}: {key!r} ({model})"
                )
            entry[field] = pair[locale]

    for entry in payload.get("catalog") or []:
        if isinstance(entry, dict):
            _entry(entry)
    # The same tier prose is repeated per class in the routing table.
    for candidates in (payload.get("classes") or {}).values():
        for entry in candidates or []:
            if isinstance(entry, dict):
                _entry(entry)
    return payload


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

    for table, what in (
        (ARENA_TEACHES, "teaches"),
        (ARENA_CLASSES, "class"),
        (ARENA_DIFFICULTIES, "difficulty"),
        (ARENA_APPROACH_LABELS, "approach label"),
        (ARENA_DETAILS, "approach detail"),
    ):
        for key, pair in table.items():
            if not pair.get("en") or not pair.get("ko"):
                raise AssertionError(f"arena {what} {key!r} missing a locale")
            if _HANGUL.search(pair["en"]):
                raise AssertionError(f"arena {what} {key!r} en carries Korean")
    for tid, fields in ARENA_PROBLEMS.items():
        for field in ("title", "prompt", "acceptance"):
            pair = fields.get(field, {})
            if not pair.get("en") or not pair.get("ko"):
                raise AssertionError(f"arena problem {tid!r} {field} missing a locale")
            if _HANGUL.search(pair["en"]):
                raise AssertionError(f"arena problem {tid!r} {field} en carries Korean")

    for table, what in (
        (CATALOG_TIERS, "catalog tier"),
        (CATALOG_REASONING, "catalog reasoning level"),
        (CATALOG_ROLES, "catalog role"),
    ):
        for key, pair in table.items():
            if not pair.get("en") or not pair.get("ko"):
                raise AssertionError(f"{what} {key!r} missing a locale")
            if _HANGUL.search(pair["en"]):
                raise AssertionError(f"{what} {key!r} en carries Korean")

    en_d, ko_d = DYNAMIC["en"], DYNAMIC["ko"]
    if set(en_d) != set(ko_d):
        raise AssertionError("DYNAMIC en/ko key sets differ")
    if set(en_d["checkLabels"]) != set(ko_d["checkLabels"]):
        raise AssertionError("DYNAMIC checkLabels keys differ across locales")
    for dkey, val in en_d.items():
        texts = (
            list(val.values()) if isinstance(val, dict)
            else ([t for pair in val for t in pair] if isinstance(val, list) else [val])
        )
        if any(_HANGUL.search(t) for t in texts):
            raise AssertionError(f"DYNAMIC en.{dkey} carries Korean")


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
        checks = entry.get("checks")
        if isinstance(checks, list):
            replacements = DYNAMIC[locale]["checkTerms"]
            for check in checks:
                if not isinstance(check, dict) or not isinstance(check.get("detail"), str):
                    continue
                detail = check["detail"]
                for source, replacement in replacements:
                    detail = detail.replace(source, replacement)
                check["detail"] = detail

    if isinstance(payload, dict):
        for coll in ("experiments", "history"):
            items = payload.get(coll)
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, dict):
                        _apply(entry)
    return payload
