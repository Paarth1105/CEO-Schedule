const calendarRoot = document.getElementById('calendar-root');
const monthSelect = document.getElementById('month-select');
const yearSelect = document.getElementById('year-select');

if (calendarRoot && monthSelect && yearSelect) {
  const today = new Date();
  const minYear = today.getFullYear() - 2;
  const maxYear = today.getFullYear() + 2;

  for (let year = minYear; year <= maxYear; year += 1) {
    const option = document.createElement('option');
    option.value = year;
    option.textContent = year;
    if (year === today.getFullYear()) option.selected = true;
    yearSelect.appendChild(option);
  }

  for (let month = 0; month < 12; month += 1) {
    const option = document.createElement('option');
    option.value = month;
    option.textContent = new Date(2000, month, 1).toLocaleString('default', { month: 'long' });
    if (month === today.getMonth()) option.selected = true;
    monthSelect.appendChild(option);
  }

  function renderCalendar() {
    const year = Number(yearSelect.value);
    const month = Number(monthSelect.value);
    calendarRoot.innerHTML = '';

    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    dayNames.forEach((name) => {
      const div = document.createElement('div');
      div.className = 'calendar-day';
      div.innerHTML = `<div class="day-number">${name}</div>`;
      calendarRoot.appendChild(div);
    });

    const firstDay = new Date(year, month, 1);
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const startDay = firstDay.getDay();

    for (let i = 0; i < startDay; i += 1) {
      const div = document.createElement('div');
      div.className = 'calendar-day outside';
      calendarRoot.appendChild(div);
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const div = document.createElement('div');
      div.className = 'calendar-day';
      const dateText = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      div.innerHTML = `<div class="day-number">${day}</div>`;
      div.style.cursor = 'pointer';
      div.addEventListener('click', () => {
        window.location.href = `/dashboard?date=${dateText}`;
      });
      const matching = (events || []).filter((entry) => entry.date === dateText);
      const isUrgent = matching.some((entry) => entry.priority === 'Urgent');
      if (isUrgent) div.classList.add('urgent');
      matching.forEach((entry) => {
        const task = document.createElement('div');
        task.className = 'task';
        task.textContent = entry.activity;
        div.appendChild(task);
      });
      calendarRoot.appendChild(div);
    }
  }

  monthSelect.addEventListener('change', renderCalendar);
  yearSelect.addEventListener('change', renderCalendar);
  renderCalendar();
}
