import { useState, useMemo } from 'react';
import type { MovieEvent } from '../types';
import { parseEventDate } from '../date';

interface CalendarViewProps {
  events: MovieEvent[];
}

const THEATER_COLORS = {
  CGV: 'bg-red-500/20 text-red-400 border-red-500/30',
  MEGABOX: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
  LOTTECINEMA: 'bg-pink-500/20 text-pink-400 border-pink-500/30',
};

const CalendarView = ({ events }: CalendarViewProps) => {
  const [currentDate, setCurrentDate] = useState(new Date());

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  // 달력 데이터 생성
  const { days, monthName } = useMemo(() => {
    const firstDayOfMonth = new Date(year, month, 1);
    const lastDayOfMonth = new Date(year, month + 1, 0);
    
    const startDay = firstDayOfMonth.getDay(); // 0 (Sun) to 6 (Sat)
    const totalDays = lastDayOfMonth.getDate();
    
    const daysArray = [];
    
    // 이전 달 공백
    for (let i = 0; i < startDay; i++) {
      daysArray.push(null);
    }
    
    // 현재 달 날짜
    for (let i = 1; i <= totalDays; i++) {
      daysArray.push(new Date(year, month, i));
    }
    
    return {
      days: daysArray,
      monthName: firstDayOfMonth.toLocaleString('ko-KR', { month: 'long', year: 'numeric' })
    };
  }, [year, month]);

  // 이벤트를 날짜별로 그룹화
  const eventsByDate = useMemo(() => {
    const grouped: Record<string, MovieEvent[]> = {};
    events.forEach(event => {
      const dateStr = parseEventDate(event.startDate).toDateString();
      if (!grouped[dateStr]) grouped[dateStr] = [];
      grouped[dateStr].push(event);
    });
    return grouped;
  }, [events]);

  const goToPreviousMonth = () => {
    setCurrentDate(new Date(year, month - 1, 1));
  };

  const goToNextMonth = () => {
    setCurrentDate(new Date(year, month + 1, 1));
  };

  const goToToday = () => {
    setCurrentDate(new Date());
  };

  const today = new Date().toDateString();

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4 sm:p-6 backdrop-blur-xl">
      {/* 달력 헤더 */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-xl font-bold text-white">{monthName}</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={goToToday}
            className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-white/10 hover:text-white transition-all active:scale-95"
          >
            오늘
          </button>
          <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/5 p-1">
            <button
              onClick={goToPreviousMonth}
              className="group flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-400 hover:bg-white/10 hover:text-white transition-all"
              title="이전 달"
            >
              <svg className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="15 19l-7-7 7-7" />
              </svg>
              <span>이전</span>
            </button>
            <div className="h-4 w-px bg-white/10" />
            <button
              onClick={goToNextMonth}
              className="group flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-400 hover:bg-white/10 hover:text-white transition-all"
              title="다음 달"
            >
              <span>다음</span>
              <svg className="h-4 w-4 transition-transform group-hover:translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto pb-2">
        <div className="min-w-[56rem] sm:min-w-0">
          {/* 요일 헤더 */}
          <div className="mb-2 grid grid-cols-7 gap-px text-center text-xs font-bold text-gray-500 uppercase tracking-wider">
            {['일', '월', '화', '수', '목', '금', '토'].map(day => (
              <div key={day} className="py-2">{day}</div>
            ))}
          </div>

          {/* 달력 그리드 */}
          <div className="grid grid-cols-7 gap-2">
            {days.map((date, idx) => {
              if (!date) return <div key={`empty-${idx}`} className="aspect-square rounded-xl bg-transparent" />;

              const dateStr = date.toDateString();
              const dayEvents = eventsByDate[dateStr] || [];
              const isToday = dateStr === today;

              return (
                <div
                  key={dateStr}
                  className={`group relative flex h-[120px] flex-col gap-1 rounded-xl border p-2 transition-all sm:h-[140px] ${
                    isToday
                      ? 'border-purple-500/50 bg-purple-500/5 ring-1 ring-purple-500/30'
                      : 'border-white/5 bg-white/5 hover:border-white/20'
                  }`}
                >
                  <div className="mb-0.5 flex items-center justify-between">
                    <span className={`text-xs font-semibold ${isToday ? 'text-purple-400' : 'text-gray-500'}`}>
                      {date.getDate()}
                    </span>
                    {dayEvents.length > 5 && (
                      <span className="rounded bg-white/5 px-1 text-[9px] font-medium text-gray-600">
                        +{dayEvents.length - 5}
                      </span>
                    )}
                  </div>

                  <div className="custom-scrollbar flex flex-1 flex-col gap-1 overflow-y-auto pr-0.5">
                    {dayEvents.map((event) => {
                      const eventTime = event.timeUnknown ? '시간 미확인' : parseEventDate(event.startDate).toLocaleTimeString('ko-KR', {
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false
                      });
                      return (
                        <a
                          key={`${event.id}-${event.startDate}`}
                          href={event.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`block truncate rounded border px-1.5 py-0.5 text-[10px] font-medium transition-all hover:scale-[1.02] active:scale-95 sm:text-[11px] ${THEATER_COLORS[event.theater]}`}
                          title={`${eventTime} | ${event.title}`}
                        >
                          <span className="mr-1 text-[9px] opacity-70 sm:text-[10px]">{eventTime}</span>
                          {event.title}
                        </a>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CalendarView;
