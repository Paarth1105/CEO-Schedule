document.addEventListener('DOMContentLoaded', () => {
  const flashMessages = document.querySelectorAll('.flash');
  flashMessages.forEach((item) => {
    setTimeout(() => item.style.display = 'none', 4000);
  });

  const userMenu = document.querySelector('.user-menu');
  const trigger = document.querySelector('.user-trigger');
  const themeSelect = document.getElementById('theme-select');
  const body = document.body;

  if (userMenu && trigger) {
    trigger.addEventListener('click', () => {
      userMenu.classList.toggle('open');
    });

    document.addEventListener('click', (event) => {
      if (!userMenu.contains(event.target)) {
        userMenu.classList.remove('open');
      }
    });
  }

  const savedTheme = localStorage.getItem('schedule-theme') || 'light';
  if (themeSelect) {
    themeSelect.value = savedTheme;
  }
  body.setAttribute('data-theme', savedTheme);

  if (themeSelect) {
    themeSelect.addEventListener('change', (event) => {
      const theme = event.target.value;
      body.setAttribute('data-theme', theme);
      localStorage.setItem('schedule-theme', theme);
    });
  }

  // Download Dropdown Interactions
  const downloadTrigger = document.getElementById('download-trigger-btn');
  const downloadWrapper = downloadTrigger ? downloadTrigger.closest('.dropdown-wrapper') : null;
  if (downloadTrigger && downloadWrapper) {
    downloadTrigger.addEventListener('click', (event) => {
      event.stopPropagation();
      downloadWrapper.classList.toggle('open');
    });
    document.addEventListener('click', (event) => {
      if (!downloadWrapper.contains(event.target)) {
        downloadWrapper.classList.remove('open');
      }
    });
  }

  // Helper to clone schedule table and strip non-exportable interactive columns/elements
  function getCleanTable() {
    const originalTable = document.querySelector('.table-fullscreen table, .table-wrap table');
    if (!originalTable) return null;

    const table = originalTable.cloneNode(true);

    // Remove all interactive toggle UI elements (.attend-toggle-ui)
    table.querySelectorAll('.attend-toggle-ui').forEach(el => el.remove());

    // Clean up participant badges/list to plain text
    table.querySelectorAll('.attendants-cell-wrapper').forEach(cell => {
      const badges = Array.from(cell.querySelectorAll('.attendant-name-badge'));
      const badgeTexts = badges.map(badge => badge.innerText.trim());
      cell.innerText = badgeTexts.length > 0 ? badgeTexts.join(', ') : 'None';
    });

    // Remove non-printable/non-exportable columns
    table.querySelectorAll('.col-google-location, .col-agenda, .col-mom, .col-action').forEach(el => el.remove());

    return table;
  }

  function getFilenamePrefix() {
    const headingEl = document.querySelector('.section-header h3');
    const title = headingEl ? headingEl.innerText.trim() : 'Schedule';
    return title.toLowerCase().replace(/[^a-z0-9]+/g, '_');
  }

  function getDocumentTitle() {
    const headingEl = document.querySelector('.section-header h3');
    return headingEl ? headingEl.innerText.trim() : 'Schedule';
  }

  // Excel (CSV) Download Option
  const downloadExcelBtn = document.getElementById('download-excel-btn');
  if (downloadExcelBtn) {
    downloadExcelBtn.addEventListener('click', (event) => {
      event.preventDefault();
      if (downloadWrapper) downloadWrapper.classList.remove('open');

      const cleanTable = getCleanTable();
      if (!cleanTable) return;

      const headers = Array.from(cleanTable.querySelectorAll('thead th')).map(th => th.innerText.trim());
      const rows = Array.from(cleanTable.querySelectorAll('tbody tr')).map(row =>
        Array.from(row.querySelectorAll('td')).map(td => td.innerText.trim())
      );

      const csvRows = [];
      csvRows.push(headers.map(h => `"${h.replace(/"/g, '""')}"`).join(','));
      rows.forEach(row => {
        if (row.length === 1 && row[0].includes('No schedule entries')) return;
        csvRows.push(row.map(cell => `"${cell.replace(/"/g, '""')}"`).join(','));
      });

      const csvContent = "\uFEFF" + csvRows.join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;

      const downloadMenu = document.getElementById('download-dropdown-menu');
      const filenameDate = downloadMenu ? downloadMenu.getAttribute('data-filename-date') : '';
      const prefix = getFilenamePrefix();
      link.download = filenameDate ? `${prefix}_${filenameDate}.csv` : `${prefix}.csv`;

      link.click();
      URL.revokeObjectURL(url);
    });
  }

  // Word (.doc Landscape) Download Option
  const downloadWordBtn = document.getElementById('download-word-btn');
  if (downloadWordBtn) {
    downloadWordBtn.addEventListener('click', (event) => {
      event.preventDefault();
      if (downloadWrapper) downloadWrapper.classList.remove('open');

      const cleanTable = getCleanTable();
      if (!cleanTable) return;

      const downloadMenu = document.getElementById('download-dropdown-menu');
      const scheduleDate = downloadMenu ? downloadMenu.getAttribute('data-schedule-date') : '';
      const filenameDate = downloadMenu ? downloadMenu.getAttribute('data-filename-date') : '';

      const docTitle = getDocumentTitle();
      const displayHeading = scheduleDate ? `${docTitle} - ${scheduleDate}` : docTitle;

      const wordHtml = `
<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
<head>
  <!--[if gte mso 9]>
  <xml>
    <w:WordDocument>
      <w:View>Print</w:View>
      <w:Zoom>90</w:Zoom>
      <w:DoNotOptimizeForBrowser/>
    </w:WordDocument>
  </xml>
  <![endif]-->
  <style>
    @page Section1 {
      size: 11in 8.5in;
      margin: 0.5in 0.5in 0.5in 0.5in;
      mso-header-margin: 0.5in;
      mso-footer-margin: 0.5in;
      mso-paper-source: 0;
    }
    div.Section1 { page: Section1; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 8px; font-family: Arial, sans-serif; font-size: 10pt; text-align: left; }
    th { background-color: #f2f2f2; font-weight: bold; }
  </style>
</head>
<body>
  <div class="Section1">
    <h2>${displayHeading}</h2>
    ${cleanTable.outerHTML}
  </div>
</body>
</html>
      `;

      const blob = new Blob(['\uFEFF' + wordHtml], { type: 'application/msword;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;

      const prefix = getFilenamePrefix();
      link.download = filenameDate ? `${prefix}_${filenameDate}.doc` : `${prefix}.doc`;

      link.click();
      URL.revokeObjectURL(url);
    });
  }

  // PDF (Print style) Download Option
  const downloadPdfBtn = document.getElementById('download-pdf-btn');
  if (downloadPdfBtn) {
    downloadPdfBtn.addEventListener('click', (event) => {
      event.preventDefault();
      if (downloadWrapper) downloadWrapper.classList.remove('open');
      window.print();
    });
  }

  function renderParticipantsIntoCell(entryId, data) {
    const listContainer = document.getElementById(`attendants-list-${entryId}`);
    if (listContainer) {
      const items = data.participants || [];
      listContainer.innerHTML = '';
      if (items.length > 0) {
        items.forEach((p, idx) => {
          const span = document.createElement('span');
          span.className = p.is_position ? 'attendant-name-badge position-chip' : 'attendant-name-badge';
          span.textContent = p.display || '';
          listContainer.appendChild(span);
          if (idx < items.length - 1) {
            listContainer.appendChild(document.createTextNode(' '));
          }
        });
      } else {
        const muted = document.createElement('span');
        muted.className = 'muted-text';
        muted.textContent = 'None';
        listContainer.appendChild(muted);
      }
    }

    const combinedBadge = document.getElementById(`combined-badge-${entryId}`);
    if (combinedBadge) {
      combinedBadge.style.display = data.is_combined ? 'inline-block' : 'none';
    }

    const shell = document.querySelector('.dashboard-shell');
    if (shell && shell.getAttribute('data-view-type') === 'combined' && data.is_combined === false) {
      window.location.reload();
    }
  }

  // Employee/Viewer: Attend/Attending AJAX toggle
  document.addEventListener('click', async (event) => {
    const attendBtn = event.target.closest('.btn-attend-toggle');
    if (!attendBtn) return;

    event.preventDefault();
    const entryId = attendBtn.getAttribute('data-entry-id');

    try {
      const response = await fetch(`/schedule/${entryId}/toggle-attendance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      if (data.status === 'success') {
        if (data.action === 'added') {
          attendBtn.classList.add('active');
          attendBtn.innerText = '✓ Attending';
        } else {
          attendBtn.classList.remove('active');
          attendBtn.innerText = 'Attend';
        }
        renderParticipantsIntoCell(entryId, data);
      }
    } catch (err) {
      console.error('Failed to toggle attendance:', err);
    }
  });

  // Inline manage attendants dropdown visibility
  document.addEventListener('click', (event) => {
    const triggerBtn = event.target.closest('.btn-manage-attendants');
    if (triggerBtn) {
      event.stopPropagation();
      const wrapper = triggerBtn.closest('.inline-manage-dropdown');

      document.querySelectorAll('.inline-manage-dropdown').forEach(d => {
        if (d !== wrapper) d.classList.remove('open');
      });

      if (wrapper) {
        wrapper.classList.toggle('open');
      }
      return;
    }

    const openDropdowns = document.querySelectorAll('.inline-manage-dropdown.open');
    openDropdowns.forEach(dropdown => {
      if (!dropdown.contains(event.target)) {
        dropdown.classList.remove('open');
      }
    });
  });

  // AJAX inline checkbox for designated positions
  document.addEventListener('change', async (event) => {
    const posChk = event.target.closest('.ajax-position-checkbox');
    if (!posChk) return;

    const entryId = posChk.getAttribute('data-entry-id');
    const posKey = posChk.getAttribute('data-position-key');

    try {
      const response = await fetch(`/schedule/${entryId}/toggle-position/${posKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      if (data.status === 'success') {
        renderParticipantsIntoCell(entryId, data);
      } else {
        posChk.checked = !posChk.checked;
      }
    } catch (err) {
      console.error('Failed to toggle position participant:', err);
      posChk.checked = !posChk.checked;
    }
  });

  // AJAX inline checkbox for individual staff/users
  document.addEventListener('change', async (event) => {
    const chk = event.target.closest('.ajax-attendant-checkbox');
    if (!chk) return;

    const entryId = chk.getAttribute('data-entry-id');
    const userId = chk.getAttribute('data-user-id');

    try {
      const response = await fetch(`/schedule/${entryId}/toggle-user-attendance/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      if (data.status === 'success') {
        renderParticipantsIntoCell(entryId, data);
      } else {
        chk.checked = !chk.checked;
      }
    } catch (err) {
      console.error('Failed to toggle user attendance:', err);
      chk.checked = !chk.checked;
    }
  });

  // Lightweight background sync polling on the dashboard (every 15 seconds when visible)
  const dashboardShell = document.querySelector('.dashboard-shell[data-schedule-version]');
  if (dashboardShell) {
    let knownVersion = dashboardShell.getAttribute('data-schedule-version');
    setInterval(async () => {
      if (document.hidden) return;
      if (document.querySelector('.inline-manage-dropdown.open')) return;
      try {
        const resp = await fetch('/api/schedule/version', { headers: { 'Accept': 'application/json' } });
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.version && knownVersion && data.version !== knownVersion) {
          window.location.reload();
        }
      } catch (e) {
        // ignore transient network errors
      }
    }, 15000);
  }

  // Dynamic weekday name display for date inputs
  const dateInputs = document.querySelectorAll('input[type="date"]');
  dateInputs.forEach(input => {
    const dayLabel = document.createElement('span');
    dayLabel.className = 'day-name-label';
    dayLabel.style.display = 'none';
    dayLabel.style.width = 'fit-content';
    dayLabel.style.marginTop = '4px';
    dayLabel.style.marginBottom = '4px';
    dayLabel.style.padding = '4px 8px';
    dayLabel.style.borderRadius = '6px';
    dayLabel.style.fontSize = '0.85rem';
    dayLabel.style.fontWeight = '600';
    dayLabel.style.background = 'var(--primary-soft)';
    dayLabel.style.color = 'var(--primary)';

    input.parentNode.insertBefore(dayLabel, input.nextSibling);

    function updateDayLabel() {
      if (input.value) {
        const parts = input.value.split('-');
        if (parts.length === 3) {
          const dateObj = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
          const options = { weekday: 'long', timeZone: 'UTC' };
          const dayName = new Intl.DateTimeFormat('en-US', options).format(dateObj);
          dayLabel.innerHTML = `Selected day: <strong>${dayName}</strong>`;
          dayLabel.style.display = 'inline-block';
        } else {
          dayLabel.innerHTML = '';
          dayLabel.style.display = 'none';
        }
      } else {
        dayLabel.innerHTML = '';
        dayLabel.style.display = 'none';
      }
    }

    input.addEventListener('change', updateDayLabel);
    input.addEventListener('input', updateDayLabel);
    updateDayLabel();
  });
});
