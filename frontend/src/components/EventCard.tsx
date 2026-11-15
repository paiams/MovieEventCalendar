import { useState } from 'react';
import type { MovieEvent } from '../types';
import { parseEventDate } from '../date';

const THEATER_STYLES: Record<string, { bg: string; text: string; border: string; glow: string }> = {
  CGV: {
    bg: 'bg-red-950/40',
    text: 'text-red-400',
    border: 'border-red-500/20',
    glow: 'hover:shadow-red-500/10',
  },
  MEGABOX: {
    bg: 'bg-purple-950/40',
    text: 'text-purple-400',
    border: 'border-purple-500/20',
    glow: 'hover:shadow-purple-500/10',
  },
  LOTTECINEMA: {
    bg: 'bg-sky-950/40',
    text: 'text-sky-400',
    border: 'border-sky-500/20',
    glow: 'hover:shadow-sky-500/10',
  },
};

const THEATER_LABELS: Record<string, string> = {
  CGV: 'CGV',
  MEGABOX: '메가박스',
  LOTTECINEMA: '롯데시네마',
};

function getTimeRemaining(startDate: string): { label: string; isLive: boolean; isPast: boolean } {
  const now = new Date();
  const target = parseEventDate(startDate);
  const diff = target.getTime() - now.getTime();

  if (diff < 0) {
    return { label: '종료됨', isLive: false, isPast: true };
  }

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  if (days > 0) {
    return { label: `D-${days}일 ${hours}시간`, isLive: false, isPast: false };
  }
  if (hours > 0) {
    return { label: `${hours}시간 ${minutes}분 후`, isLive: false, isPast: false };
  }
  if (minutes > 0) {
    return { label: `${minutes}분 후`, isLive: true, isPast: false };
  }
  return { label: '곧 시작!', isLive: true, isPast: false };
}

function formatDate(dateStr: string, timeUnknown = false): string {
  const d = parseEventDate(dateStr);
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const weekday = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  const hours = d.getHours().toString().padStart(2, '0');
  const minutes = d.getMinutes().toString().padStart(2, '0');
  return `${month}/${day}(${weekday}) ${timeUnknown ? '시간 미확인' : `${hours}:${minutes}`}`;
}

function buildGoogleCalendarUrl(event: MovieEvent): string {
  const start = parseEventDate(event.startDate);
  const end = new Date(start.getTime() + (event.timeUnknown ? 24 * 60 : 30) * 60 * 1000);

  const fmt = (d: Date) =>
    event.timeUnknown
      ? d.toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' }).replace(/-/g, '')
      : d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');

  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: `[${THEATER_LABELS[event.theater]}] ${event.title} - ${event.category}`,
    dates: `${fmt(start)}/${fmt(end)}`,
    details: `${event.category} 이벤트\n${event.timeUnknown ? '시작 시간 미확인 — 상세 페이지를 확인하세요.\n' : ''}예매 링크: ${event.url}`,
    location: THEATER_LABELS[event.theater],
  });

  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

interface EventCardProps {
  event: MovieEvent;
}

export default function EventCard({ event }: EventCardProps) {
  const [imgError, setImgError] = useState(false);
  const style = THEATER_STYLES[event.theater] || THEATER_STYLES.CGV;
  const remaining = event.timeUnknown
    ? { label: '시간 미확인', isLive: false, isPast: false }
    : getTimeRemaining(event.startDate);

  return (
    <div
      className={`group relative overflow-hidden rounded-2xl border ${style.border} ${style.bg} backdrop-blur-sm transition-all duration-300 hover:scale-[1.02] hover:shadow-2xl ${style.glow} ${remaining.isPast ? 'opacity-50' : ''}`}
    >
      {/* 이미지 영역 */}
      <div className="relative aspect-[16/9] overflow-hidden bg-gray-900">
        {event.imageUrl && !imgError ? (
          <img
            src={event.imageUrl}
            alt={event.title}
            className="h-full w-full object-cover"
            onError={() => setImgError(true)}
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-gray-800 to-gray-900">
            <span className="text-4xl">🎬</span>
          </div>
        )}
        {/* 오버레이 그라데이션 */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />

        {/* 타이머 뱃지 */}
        <div className="absolute top-3 right-3">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-bold backdrop-blur-md ${
              remaining.isPast
                ? 'bg-gray-500/40 text-gray-300'
                : remaining.isLive
                  ? 'bg-emerald-500/30 text-emerald-300 animate-pulse'
                  : 'bg-black/50 text-white'
            }`}
          >
            {remaining.isLive && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />}
            {remaining.label}
          </span>
        </div>
      </div>

      {/* 정보 영역 */}
      <div className="p-5 space-y-3">
        <div>
          <h3 className="text-xl font-bold text-white leading-tight line-clamp-2">
            {event.title}
          </h3>
          <p className={`mt-1.5 text-sm font-medium ${style.text}`}>
            {THEATER_LABELS[event.theater]} · {event.category}
          </p>
        </div>

        <div className="flex items-center gap-2 text-sm text-gray-400">
          <svg className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <span>{formatDate(event.startDate, event.timeUnknown)}</span>
        </div>

        {/* 액션 버튼 */}
        <div className="flex gap-2 pt-1">
          <a
            href={event.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 rounded-xl bg-white/10 py-2.5 text-center text-base font-semibold text-white backdrop-blur-sm transition-all hover:bg-white/20 active:scale-95"
          >
            이벤트 페이지
          </a>
          <a
            href={buildGoogleCalendarUrl(event)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center rounded-xl bg-white/10 px-3 py-2.5 text-white backdrop-blur-sm transition-all hover:bg-white/20 active:scale-95"
            title="Google 캘린더에 추가"
            aria-label={`${event.title} Google 캘린더에 추가`}
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </a>
        </div>
      </div>
    </div>
  );
}
