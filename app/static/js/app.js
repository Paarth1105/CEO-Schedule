document.addEventListener('DOMContentLoaded', () => {
  const flashMessages = document.querySelectorAll('.flash');
  flashMessages.forEach((item) => {
    setTimeout(() => item.style.display = 'none', 3000);
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

    // Clean up attendant badges/list if needed to plain text
    table.querySelectorAll('.attendants-cell-wrapper').forEach(cell => {
      const badges = Array.from(cell.querySelectorAll('.attendant-name-badge'));
      const badgeTexts = badges.map(badge => badge.innerText.trim());
      if (badgeTexts.length > 0) {
        cell.innerText = badgeTexts.join(', ');
      } else {
        cell.innerText = 'None';
      }
    });

    // Check headers for "Action" column and filter it out
    const headers = Array.from(table.querySelectorAll('thead th'));
    const actionIndex = headers.findIndex(th => th.innerText.trim() === 'Action');
    if (actionIndex !== -1) {
      // Remove Action header
      headers[actionIndex].remove();
      // Remove Action cell in each row
      table.querySelectorAll('tbody tr').forEach(row => {
        const cells = Array.from(row.querySelectorAll('td'));
        if (cells[actionIndex]) {
          cells[actionIndex].remove();
        }
      });
    }

    return table;
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
      // Header row
      csvRows.push(headers.map(h => `"${h.replace(/"/g, '""')}"`).join(','));
      // Data rows
      rows.forEach(row => {
        if (row.length === 1 && row[0].includes('No schedule entries')) {
          return;
        }
        csvRows.push(row.map(cell => `"${cell.replace(/"/g, '""')}"`).join(','));
      });

      const csvContent = "\uFEFF" + csvRows.join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'schedule.csv';
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

      // Build landscape oriented HTML for Microsoft Word
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
      size: 11in 8.5in; /* Landscape orientation */
      margin: 0.5in 0.5in 0.5in 0.5in;
      mso-header-margin: 0.5in;
      mso-footer-margin: 0.5in;
      mso-paper-source: 0;
    }
    div.Section1 {
      page: Section1;
    }
    table {
      border-collapse: collapse;
      width: 100%;
    }
    th, td {
      border: 1px solid #ccc;
      padding: 8px;
      font-family: Arial, sans-serif;
      font-size: 10pt;
      text-align: left;
    }
    th {
      background-color: #f2f2f2;
      font-weight: bold;
    }
  </style>
</head>
<body>
  <div class="Section1">
    <h2>CEO Schedule Overview</h2>
    ${cleanTable.outerHTML}
  </div>
</body>
</html>
      `;

      const blob = new Blob(['\uFEFF' + wordHtml], { type: 'application/msword;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'schedule.doc';
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  // Employee: Attend/Attending AJAX toggle
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
        // Toggle button state classes and text
        if (data.action === 'added') {
          attendBtn.classList.add('active');
          attendBtn.innerText = '✓ Attending';
        } else {
          attendBtn.classList.remove('active');
          attendBtn.innerText = 'Attend';
        }
        
        // Dynamic update of the attendants names list
        const listContainer = document.getElementById(`attendants-list-${entryId}`);
        if (listContainer) {
          if (data.attendants.length > 0) {
            listContainer.innerHTML = data.attendants.map(name => 
              `<span class="attendant-name-badge">${name}</span>`
            ).join(', ');
          } else {
            listContainer.innerHTML = '<span class="muted-text">None</span>';
          }
        }
      }
    } catch (err) {
      console.error('Failed to toggle attendance:', err);
    }
  });

  // Admin (PA/SA): Toggle inline manage attendants dropdown visibility
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('.btn-manage-attendants');
    if (trigger) {
      event.stopPropagation();
      const wrapper = trigger.closest('.inline-manage-dropdown');
      
      // Close other open inline dropdowns first
      document.querySelectorAll('.inline-manage-dropdown').forEach(d => {
        if (d !== wrapper) d.classList.remove('open');
      });
      
      if (wrapper) {
        wrapper.classList.toggle('open');
      }
      return;
    }
    
    // Close dropdowns when clicking outside
    const openDropdowns = document.querySelectorAll('.inline-manage-dropdown.open');
    openDropdowns.forEach(dropdown => {
      if (!dropdown.contains(event.target)) {
        dropdown.classList.remove('open');
      }
    });
  });

  // Admin (PA/SA): AJAX inline checkbox attendant toggles
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
        // Dynamic update of the attendants names list
        const listContainer = document.getElementById(`attendants-list-${entryId}`);
        if (listContainer) {
          if (data.attendants.length > 0) {
            listContainer.innerHTML = data.attendants.map(name => 
              `<span class="attendant-name-badge">${name}</span>`
            ).join(', ');
          } else {
            listContainer.innerHTML = '<span class="muted-text">None</span>';
          }
        }
      } else {
        chk.checked = !chk.checked; // Revert state if backend returned failure
      }
    } catch (err) {
      console.error('Failed to toggle user attendance:', err);
      chk.checked = !chk.checked; // Revert state on network error
    }
  });
});

