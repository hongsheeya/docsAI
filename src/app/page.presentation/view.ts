import { OnInit, OnDestroy } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit, OnDestroy {
    constructor(public service: Service) { }

    public current: number = 0;
    public overview: boolean = false;
    public fullscreen: boolean = false;

    public slides: any[] = [
        {
            type: 'cover',
            badge: '모델 포트폴리오 · 2026-06-22',
            title: 'FallAI 모델 포트폴리오',
            subtitle: 'RF-Dual 운영 모델, XG-Posture, AI-Hub 82/173 표정·상태 보조, 가림 보조 모델을 한눈에 정리',
            stats: [
                { label: 'RF-Fall 운영 F1', value: '98.1%', tone: 'emerald' },
                { label: 'XG-Posture F1', value: '94.3%', tone: 'cyan' },
                { label: '가림 보조 Sequence F1', value: '95.96%', tone: 'orange' },
                { label: 'AI-Hub 82 Macro F1', value: '87.5%', tone: 'violet' },
            ],
        },
        {
            type: 'table',
            badge: '1 / 파이프라인',
            title: '이번 개선 파이프라인',
            accent: 'emerald',
            tables: [
                {
                    title: '주 판정과 보조 evidence 흐름',
                    headers: ['단계', '모델/처리', '역할', '이번 발표 포인트'],
                    rows: [
                        ['1', 'Pose/BBox feature', '사람 위치, 자세, 이동량, visibility 추출', '프라이버시 화면은 skeleton-only로 표시'],
                        ['2', 'RF-Fall v2', '낙상/비낙상 주 판정', '운영 F1 98.1%, Acc 96.8%, Recall 99.3%'],
                        ['3', 'XG-Posture', '비낙상 구간 행동 설명', '운영 F1 94.3%, Acc 94.3%'],
                        ['4', 'Occlusion-Aux', '하체가림 전처리로 만든 보조 판단', 'Sequence F1 95.96%로 목표 달성, 반복 학습 중단'],
                        ['5', 'FacialRisk-Aux', '표정/주의저하 근거를 하나의 보조 evidence로 합산', 'AI-Hub 82는 87.5% plateau 원인 제거 후 seed sweep 재학습 중'],
                    ],
                },
            ],
            note: 'RF-Fall이 주 판정이고, 가림과 표정은 약한 구간을 보조한다. LLM은 판정을 뒤집지 않고 근거를 설명한다.',
        },
        {
            type: 'table',
            badge: '2 / 이번 발표의 두 축',
            title: '표정 보조와 가림 보조를 같이 검증',
            accent: 'orange',
            tables: [
                {
                    title: '둘 다 주 모델을 대체하지 않고 약점 구간을 보강한다',
                    headers: ['보조모델', '왜 만들었나', '검증 결과', '현재 결론'],
                    rows: [
                        ['Occlusion-Aux', '하체가 침대/가구/화면 밖으로 가려질 때 stand/sit/lie가 흔들림', 'Sequence F1 95.96% · Window F1 91.13%', '목표 달성 완료. 이제 표정/상태 모델을 우선 개선'],
                        ['FacialRisk-Aux', '낙상 near-miss에서 표정/주의저하 evidence가 빠져 FN이 남음', 'AI-Hub 82 Macro F1 87.5% · AI-Hub 173 Macro F1 93.24%', '82는 고정 seed 반복과 FP precision 병목을 제거하는 중'],
                    ],
                },
            ],
            note: '이번 발표의 중심은 “표정만”이 아니라, RF-Fall의 약한 구간을 두 보조모델로 어떻게 보강했는지다.',
        },
        {
            type: 'table',
            badge: '3 / FacialRisk-Aux',
            title: '표정 보조모델: 82와 173을 왜 나눴나',
            accent: 'cyan',
            tables: [
                {
                    title: '내부는 2개 모델, 외부는 1개 보조점수',
                    headers: ['표시 이름', '기존 번호', '학습 목적', '현재 성능', '운영 해석'],
                    rows: [
                        ['EmotionGuard-82', 'AI-Hub 82', 'distress/non-distress 운영 보조', 'Acc 87.52% · Macro F1 87.50%', 'distress recall은 높지만 precision 병목이 있어 seed/crop/weight 조합으로 개선 중'],
                        ['DrowsyState-173', 'AI-Hub 173', '졸음/하품/주의저하 5-class', 'Acc 90.2% · Macro F1 93.24%', '졸음/하품처럼 명확한 상태 근거가 비교적 안정적'],
                        ['FacialRisk-Aux', '통합 출력', '두 모델의 evidence를 late fusion', '단일 support score로 표시', '화면과 발표에서는 표정 보조모델 하나처럼 설명'],
                    ],
                },
            ],
            note: '완전한 단일 모델로 재학습하지 않은 이유는 82와 173의 라벨 체계가 서로 다르기 때문이다. 지금은 내부 2개 모델, 외부 1개 보조점수 구조가 가장 안전하다.',
        },
        {
            type: 'table',
            badge: '4 / 판정 도움 여부',
            title: '표정 보조가 낙상 판정에 도움이 됐나',
            accent: 'rose',
            tables: [
                {
                    title: '같은 threshold로 비교한 AI-Hub 71641 확장 검증',
                    headers: ['검증 항목', '결과', '의미'],
                    rows: [
                        ['동일 테스트 샘플', '100개', 'AI-Hub 71641에서 낙상 50 / 비낙상 50 균형 추출'],
                        ['표정 보조 전후 F1', '0.9149 → 0.9149', '순수 score A/B에서는 최종 판정 변화 없음'],
                        ['Recall', '0.8600 → 0.8600', 'FN 7건 유지'],
                        ['실제 반영 건수', '1/100', 'support 14건, blocked 10건, 얼굴 미검출 65건'],
                        ['판정 변화', '0건', 'helpful 0건, harmful 0건'],
                    ],
                },
            ],
            note: '말할 결론: 소규모 검증의 개선 신호를 100개로 확장했지만 최종 판정 개선은 확인되지 않았다. 얼굴 미검출 65/100이라 ROI 품질과 실제 설치각 얼굴 데이터가 핵심이다.',
        },
        {
            type: 'table',
            badge: '5 / 표정 한계',
            title: '표정 보조 한계와 다음 방향',
            accent: 'orange',
            tables: [
                {
                    title: '원인과 다음 조치',
                    headers: ['문제', '왜 중요한가', '다음 조치'],
                    rows: [
                        ['얼굴이 작거나 안 보임', '100개 중 얼굴 미검출 65건', '상체/전체 프레임 fallback을 추가했고, 실제 얼굴 검출률 지표로 gate'],
                        ['82 표정모델 plateau', '87.5% 후보가 고정 seed와 같은 레시피로 반복되어 실제 탐색이 멈춤', 'distress FP를 줄이는 crop/weight/smoothing/validation seed sweep으로 재학습'],
                        ['173 도메인 차이', '운전자 상태 데이터라 병실/실내 낙상과 완전히 같지 않음', '졸음/하품/눈감김 evidence로만 제한'],
                        ['실환경 데이터 부족', '낙상 전후 표정, 누운 상태 얼굴, 가림 얼굴이 부족', '실제 설치각 데이터로 near-miss rescue 기준 재검증'],
                    ],
                },
            ],
        },
        {
            type: 'table',
            badge: '6 / 하체가림 전처리',
            title: '하체가림 전처리 보조모델',
            accent: 'violet',
            tables: [
                {
                    title: '왜 만들고 어떻게 학습했나',
                    headers: ['항목', '내용'],
                    rows: [
                        ['왜 만들었나', '하체가 침대/가구/화면 밖으로 가려지면 stand/sit/lie 판단이 흔들려 미확인이나 오분류가 늘어남'],
                        ['전처리', '기존 posture window에서 하체 영역을 0.55/0.62/0.70 비율로 가림 처리'],
                        ['누수 방지', '원본과 가림 샘플을 같은 group으로 묶어 train/validation 동시 유입 방지'],
                        ['학습', 'ExtraTrees balanced · 105 feature · lower-body occlusion window 4,500개'],
                        ['적용', '하체 visibility가 낮거나 posture confidence가 낮을 때 기존 XG-Posture를 보조'],
                    ],
                },
            ],
        },
        {
            type: 'table',
            badge: '7 / 가림 효과',
            title: '가림 보조모델은 도움이 됐나',
            accent: 'emerald',
            tables: [
                {
                    title: '효과를 숫자 대신 결론 중심으로 정리',
                    headers: ['비교', '수치', '해석'],
                    rows: [
                        ['기존 XG-Posture', 'F1 0.6513 / Acc 0.6602', '일반 행동분류 기준. 하체가림 hard-case에 약함'],
                        ['Occlusion-Aux', 'Sequence F1 95.96% / Window F1 91.13%', '가림 전처리 조건에서 목표 달성, 반복 학습 중단'],
                        ['RF 주 판정 기여', 'occlusion_fall_risk rank 4/65, importance 0.0564', '가림 관련 feature가 낙상 판정에서도 상위 근거로 사용됨'],
                    ],
                },
            ],
            note: '가림 보조모델은 목표 95%를 넘겼으므로 더 돌리지 않고, 같은 자원은 AI-Hub 82/173 등 미달 모델 개선에 우선 배정한다.',
        },
        {
            type: 'screenshot',
            badge: '8 / 프라이버시 모드',
            title: 'Skeleton-only 화면으로 사용자 노출 최소화',
            accent: 'emerald',
            image: '/assets/pres/skeleton-privacy-mode.png',
            points: [
                '사용자 화면은 원본 인물 픽셀을 숨기고 skeleton landmark만 표시한다.',
                '관리자 확인용으로 원본/스켈레톤 전환 버튼을 제공한다.',
                '분석은 유지하되, 일반 사용자에게는 사람이 직접 보이지 않게 하는 방향이다.',
            ],
        },
        {
            type: 'table',
            badge: '9 / 결론',
            title: '최종 결론',
            accent: 'slate',
            tables: [
                {
                    title: '무엇이 효과 있었고, 무엇이 아직 실패인가',
                    headers: ['항목', '현재 결론', '다음 개선'],
                    rows: [
                        ['표정 보조', 'AI-Hub 82는 87.5% plateau. 고정 seed 반복과 잘못된 clean 레시피를 제거', 'precision 병목을 줄이는 새 후보를 백그라운드 학습 중'],
                        ['82+173 통합', '지금은 내부 2개 모델을 FacialRisk-Aux 하나의 보조점수로 합산', '공통 라벨(normal/distress/drowsy/unknown) 데이터가 생기면 단일 모델 재학습'],
                        ['가림 보조', 'Sequence F1 95.96%로 목표 달성', '추가 반복보다 실제 침대/가구 가림 데이터 확보가 다음 단계'],
                        ['발표 메시지', '가림은 목표 달성, 표정은 현재 최우선 개선 대상', '표정은 FP precision과 얼굴 ROI 품질을 같이 잡는 것이 핵심'],
                    ],
                },
            ],
        },
    ];

    public get slide(): any {
        return this.slides[this.current];
    }

    public get total(): number {
        return this.slides.length;
    }

    public get progress(): number {
        return ((this.current + 1) / this.total) * 100;
    }

    public async ngOnInit() {
        await this.service.init(this);
        window.addEventListener('keydown', this._keyHandler);
        document.addEventListener('fullscreenchange', this._fsHandler);
        await this.service.render();
    }

    public ngOnDestroy() {
        window.removeEventListener('keydown', this._keyHandler);
        document.removeEventListener('fullscreenchange', this._fsHandler);
    }

    private _keyHandler = (e: KeyboardEvent) => {
        if (this.overview) {
            if (e.key === 'Escape') {
                this.overview = false;
                this.service.render();
            }
            return;
        }
        if (e.key === 'ArrowRight' || e.key === ' ') {
            e.preventDefault();
            this.next();
        } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            this.prev();
        } else if (e.key === 'Escape') {
            if (this.fullscreen) {
                document.exitFullscreen();
            } else {
                this.service.href('/');
            }
        } else if (e.key === 'Tab') {
            e.preventDefault();
            this.toggleOverview();
        } else if (e.key === 'f' || e.key === 'F') {
            e.preventDefault();
            this.toggleFullscreen();
        }
    };

    private _fsHandler = () => {
        this.fullscreen = !!document.fullscreenElement;
        this.service.render();
    };

    public toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    }

    public next() {
        if (this.current < this.total - 1) {
            this.current++;
            this.service.render();
        }
    }

    public prev() {
        if (this.current > 0) {
            this.current--;
            this.service.render();
        }
    }

    public goTo(i: number) {
        this.current = i;
        this.overview = false;
        this.service.render();
    }

    public toggleOverview() {
        this.overview = !this.overview;
        this.service.render();
    }

    public truncate(s: string, len: number = 30): string {
        s = s || '';
        return s.length > len ? s.substring(0, len) + '...' : s;
    }

    public matrixColumns(labels: any[]): string {
        const count = Array.isArray(labels) ? labels.length : 5;
        return `96px repeat(${count}, minmax(68px, 1fr))`;
    }

    public heatStyle(value: number, max: number): any {
        const v = Number(value || 0);
        const m = Math.max(Number(max || 1), 1);
        const t = Math.max(0, Math.min(1, v / m));
        const alpha = 0.08 + t * 0.72;
        return {
            background: `rgba(20, 184, 166, ${alpha})`,
            color: t > 0.55 ? '#042f2e' : '#164e63',
            fontWeight: t > 0.45 ? 800 : 600,
        };
    }

    public toneClass(tone: string): string {
        return 'tone-' + (tone || 'indigo');
    }

    public accentClass(accent: string, variant: string = 'bg'): string {
        const map: any = {
            indigo: { bg: 'bg-indigo-600', light: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-200', badge: 'bg-indigo-100 text-indigo-700' },
            violet: { bg: 'bg-violet-600', light: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200', badge: 'bg-violet-100 text-violet-700' },
            rose: { bg: 'bg-rose-600', light: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200', badge: 'bg-rose-100 text-rose-700' },
            sky: { bg: 'bg-sky-600', light: 'bg-sky-50', text: 'text-sky-700', border: 'border-sky-200', badge: 'bg-sky-100 text-sky-700' },
            emerald: { bg: 'bg-emerald-600', light: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', badge: 'bg-emerald-100 text-emerald-700' },
            amber: { bg: 'bg-amber-500', light: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', badge: 'bg-amber-100 text-amber-700' },
            orange: { bg: 'bg-orange-500', light: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200', badge: 'bg-orange-100 text-orange-700' },
            cyan: { bg: 'bg-cyan-600', light: 'bg-cyan-50', text: 'text-cyan-700', border: 'border-cyan-200', badge: 'bg-cyan-100 text-cyan-700' },
            green: { bg: 'bg-green-600', light: 'bg-green-50', text: 'text-green-700', border: 'border-green-200', badge: 'bg-green-100 text-green-700' },
            red: { bg: 'bg-red-600', light: 'bg-red-50', text: 'text-red-700', border: 'border-red-200', badge: 'bg-red-100 text-red-700' },
            slate: { bg: 'bg-slate-600', light: 'bg-slate-50', text: 'text-slate-700', border: 'border-slate-200', badge: 'bg-slate-100 text-slate-700' },
        };
        return (map[accent] || map.indigo)[variant] || '';
    }

    public colClass(color: string): string {
        return this.accentClass(color, 'border') + ' ' + this.accentClass(color, 'light');
    }

    public colTextClass(color: string): string {
        return this.accentClass(color, 'text');
    }

    public pipelineHighlightClass(step: any): string {
        return step.highlight ? 'ring-2 ring-violet-400 bg-white shadow-lg' : 'bg-white/80';
    }

    public portfolioCoverStats(): any[] {
        const cover = this.slides.find((item: any) => item?.type === 'cover');
        return Array.isArray(cover?.stats) ? cover.stats : [];
    }

    public portfolioExportDateText(): string {
        return new Date().toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
        });
    }

    public exportPortfolioPdf() {
        const previousTitle = document.title;
        document.title = `FallAI-portfolio-${new Date().toISOString().slice(0, 10)}`;
        const restoreTitle = () => {
            document.title = previousTitle;
            window.removeEventListener('afterprint', restoreTitle);
        };
        window.addEventListener('afterprint', restoreTitle);
        setTimeout(() => window.print(), 80);
    }
}
