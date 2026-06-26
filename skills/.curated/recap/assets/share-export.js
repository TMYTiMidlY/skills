
(function() {
    'use strict';

    var scrollContainer = document.querySelector('.scroll-container');

    // --- Collapse/Expand ---
    document.querySelectorAll('.entry-header').forEach(function(header) {
        header.addEventListener('click', function(e) {
            if (e.target.closest('.entry-time')) return;
            header.closest('.entry').classList.toggle('collapsed');
        });
        header.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                header.closest('.entry').classList.toggle('collapsed');
            }
        });
    });

    var collapseAllBtn = document.getElementById('collapse-all');
    var expandAllBtn = document.getElementById('expand-all');
    if (collapseAllBtn) {
        collapseAllBtn.addEventListener('click', function() {
            document.querySelectorAll('.entry').forEach(function(e) { e.classList.add('collapsed'); });
        });
    }
    if (expandAllBtn) {
        expandAllBtn.addEventListener('click', function() {
            document.querySelectorAll('.entry').forEach(function(e) { e.classList.remove('collapsed'); });
        });
    }

    // --- Search ---
    var searchInput = document.getElementById('search-input');
    var searchTimeout = null;

    function clearHighlights() {
        document.querySelectorAll('.search-highlight').forEach(function(el) {
            var parent = el.parentNode;
            parent.replaceChild(document.createTextNode(el.textContent), el);
            parent.normalize();
        });
    }

    function highlightText(node, query) {
        if (!query) return;
        var lowerQuery = query.toLowerCase();
        var walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, null);
        var textNodes = [];
        while (walker.nextNode()) textNodes.push(walker.currentNode);
        textNodes.forEach(function(tn) {
            var text = tn.textContent;
            var idx = text.toLowerCase().indexOf(lowerQuery);
            if (idx === -1) return;
            var before = document.createTextNode(text.substring(0, idx));
            var mark = document.createElement('span');
            mark.className = 'search-highlight';
            mark.textContent = text.substring(idx, idx + query.length);
            var after = document.createTextNode(text.substring(idx + query.length));
            var parent = tn.parentNode;
            parent.insertBefore(before, tn);
            parent.insertBefore(mark, tn);
            parent.insertBefore(after, tn);
            parent.removeChild(tn);
        });
    }

    function doSearch() {
        var query = searchInput ? searchInput.value.trim() : '';
        clearHighlights();
        var entries = document.querySelectorAll('.main-container > .entry');
        if (!query) {
            entries.forEach(function(e) { e.classList.remove('search-hidden'); });
            syncSidebarFilters();
            return;
        }
        var lq = query.toLowerCase();
        entries.forEach(function(entry) {
            var text = entry.textContent.toLowerCase();
            if (text.indexOf(lq) !== -1) {
                entry.classList.remove('search-hidden');
                highlightText(entry, query);
            } else {
                entry.classList.add('search-hidden');
            }
        });
        syncSidebarFilters();
    }

    if (searchInput) {
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(doSearch, 150);
        });
    }

    // --- Type Filtering ---
    var activeFilters = new Set();
    var filterPills = document.querySelectorAll('.filter-pill');
    filterPills.forEach(function(pill) {
        var type = pill.getAttribute('data-filter-type');
        activeFilters.add(type);
        pill.classList.add('active');
        pill.addEventListener('click', function() {
            if (activeFilters.has(type)) {
                activeFilters.delete(type);
                pill.classList.remove('active');
                pill.classList.add('inactive');
            } else {
                activeFilters.add(type);
                pill.classList.add('active');
                pill.classList.remove('inactive');
            }
            applyFilters();
        });
    });

    var compactBtn = document.getElementById('compact-mode');
    var compactActive = false;
    if (compactBtn) {
        compactBtn.addEventListener('click', function() {
            compactActive = !compactActive;
            compactBtn.classList.toggle('active', compactActive);
            if (compactActive) {
                filterPills.forEach(function(pill) {
                    var type = pill.getAttribute('data-filter-type');
                    if (type === 'user' || type === 'copilot') {
                        activeFilters.add(type);
                        pill.classList.add('active');
                        pill.classList.remove('inactive');
                    } else {
                        activeFilters.delete(type);
                        pill.classList.remove('active');
                        pill.classList.add('inactive');
                    }
                });
            } else {
                filterPills.forEach(function(pill) {
                    var type = pill.getAttribute('data-filter-type');
                    activeFilters.add(type);
                    pill.classList.add('active');
                    pill.classList.remove('inactive');
                });
            }
            applyFilters();
        });
    }

    function applyFilters() {
        document.querySelectorAll('.main-container > .entry').forEach(function(entry) {
            var type = entry.getAttribute('data-type');
            if (activeFilters.has(type)) {
                entry.classList.remove('filter-hidden');
            } else {
                entry.classList.add('filter-hidden');
            }
        });
        syncSidebarFilters();
    }

    // --- Keyboard Navigation ---
    var focusedIndex = -1;
    function getVisibleEntries() {
        return Array.from(document.querySelectorAll('.main-container > .entry')).filter(function(e) {
            return !e.classList.contains('filter-hidden') && !e.classList.contains('search-hidden');
        });
    }
    function setFocus(idx) {
        var entries = getVisibleEntries();
        if (entries[focusedIndex]) entries[focusedIndex].classList.remove('focused');
        focusedIndex = idx;
        if (focusedIndex >= 0 && focusedIndex < entries.length) {
            entries[focusedIndex].classList.add('focused');
            entries[focusedIndex].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    }

    document.addEventListener('keydown', function(e) {
        if (e.target.tagName === 'INPUT') {
            if (e.key === 'Escape') { searchInput.blur(); searchInput.value = ''; doSearch(); }
            return;
        }
        var entries = getVisibleEntries();
        if (e.key === 'j') { setFocus(Math.min(focusedIndex + 1, entries.length - 1)); }
        else if (e.key === 'k') { setFocus(Math.max(focusedIndex - 1, 0)); }
        else if (e.key === 'Enter' && focusedIndex >= 0 && focusedIndex < entries.length) {
            entries[focusedIndex].classList.toggle('collapsed');
        }
        else if (e.key === '/') { e.preventDefault(); if (searchInput) searchInput.focus(); }
        else if (e.key === 'Escape') {
            if (focusedIndex >= 0) {
                entries[focusedIndex].classList.remove('focused');
                focusedIndex = -1;
            }
        }
    });

    // --- Theme Toggle ---
    var themeBtn = document.getElementById('theme-toggle');
    function setTheme(theme) {
        var el = document.documentElement;
        el.setAttribute('data-color-mode', theme);
        el.setAttribute('data-light-theme', 'light');
        el.setAttribute('data-dark-theme', 'dark');
        try { localStorage.setItem('copilot-share-theme', theme); } catch(e) {}
        if (themeBtn) themeBtn.textContent = theme === 'dark' ? '\u2600' : '\u263E';
    }
    (function initTheme() {
        var saved = null;
        try { saved = localStorage.getItem('copilot-share-theme'); } catch(e) {}
        if (saved === 'light' || saved === 'dark') { setTheme(saved); }
        else { setTheme('dark'); }
    })();
    if (themeBtn) {
        themeBtn.addEventListener('click', function() {
            var current = document.documentElement.getAttribute('data-color-mode') || 'dark';
            setTheme(current === 'dark' ? 'light' : 'dark');
        });
    }

    // --- Sidebar Minimap ---
    var sidebar = document.getElementById('sidebar');
    var sidebarBtn = document.getElementById('sidebar-toggle');
    var mainContainer = document.querySelector('.main-container');

    function getMapLabel(type, fullLabel) {
        var shortLabels = {
            'user': 'User', 'copilot': 'Copilot', 'error': 'Error',
            'reasoning': 'Reasoning', 'info': 'Info', 'warning': 'Warning',
            'handoff': 'Handoff', 'compaction': 'Compacted',
            'task_complete': 'Complete', 'notification': 'Notification'
        };
        if (shortLabels[type]) return shortLabels[type];
        var dashIdx = fullLabel.indexOf(' - ');
        if (dashIdx > 0) return fullLabel.substring(0, dashIdx);
        return fullLabel;
    }

    function createSidebarEntry(type, label, entryIndex, targetEl, isNested) {
        var se = document.createElement('div');
        se.className = 'sidebar-entry' + (isNested ? ' nested' : '');
        if (entryIndex !== null) se.setAttribute('data-entry-index', entryIndex);

        var dot = document.createElement('span');
        dot.className = 'sidebar-indicator';
        dot.setAttribute('data-type', type);
        se.appendChild(dot);

        var span = document.createElement('span');
        span.className = 'sidebar-label';
        span.textContent = getMapLabel(type, label);
        se.appendChild(span);

        var tip = label;
        if (entryIndex !== null) tip += ' (#' + (parseInt(entryIndex) + 1) + ')';
        se.title = tip;

        se.addEventListener('click', function() {
            // Immediately highlight this sidebar entry
            document.querySelectorAll('.sidebar-entry.active').forEach(function(el) {
                el.classList.remove('active');
            });
            se.classList.add('active');

            // Suppress scroll-based sync while the smooth scroll is in progress
            navClickActive = true;
            clearTimeout(navClickTimer);
            navClickTimer = setTimeout(function() { navClickActive = false; }, 800);

            // Flash the target entry in the main content
            targetEl.classList.remove('nav-flash');
            void targetEl.offsetWidth;
            targetEl.classList.add('nav-flash');

            targetEl.scrollIntoView({ block: 'start', behavior: 'smooth' });
        });
        return se;
    }
    var navClickActive = false;
    var navClickTimer;

    if (sidebarBtn && sidebar) {
        sidebarBtn.addEventListener('click', function() {
            sidebar.classList.toggle('visible');
            var isVis = sidebar.classList.contains('visible');
            sidebarBtn.classList.toggle('active', isVis);
            if (mainContainer) mainContainer.classList.toggle('sidebar-visible', isVis);
        });

        document.querySelectorAll('.main-container > .entry').forEach(function(entry) {
            var type = entry.getAttribute('data-type');
            var labelEl = entry.querySelector('.entry-label');
            var label = labelEl ? labelEl.textContent.trim() : type;
            var idx = entry.getAttribute('data-index');

            var se = createSidebarEntry(type, label, idx, entry, false);
            sidebar.appendChild(se);

            // For group entries, add indented nested entries
            if (type === 'group') {
                entry.querySelectorAll('.nested-entries > .entry').forEach(function(nested) {
                    var nType = nested.getAttribute('data-type') || 'tool';
                    var nLabelEl = nested.querySelector('.entry-label');
                    var nLabel = nLabelEl ? nLabelEl.textContent.trim() : nType;
                    var nIdx = nested.getAttribute('data-index');
                    var nse = createSidebarEntry(nType, nLabel, nIdx, nested, true);
                    sidebar.appendChild(nse);
                });
            }
        });
    }

    // --- Sidebar Scroll Position Tracking ---
    function syncSidebarHighlight() {
        if (!sidebar || !sidebar.classList.contains('visible')) return;
        if (navClickActive) return;
        var entries = document.querySelectorAll('.main-container > .entry');
        var viewMid = scrollContainer.scrollTop + scrollContainer.clientHeight / 3;
        var closest = null;
        var closestDist = Infinity;
        entries.forEach(function(e) {
            if (e.classList.contains('filter-hidden') || e.classList.contains('search-hidden')) return;
            var top = e.offsetTop;
            var d = Math.abs(top - viewMid);
            if (d < closestDist) { closestDist = d; closest = e; }
        });
        document.querySelectorAll('.sidebar-entry.active').forEach(function(el) {
            el.classList.remove('active');
        });
        if (closest) {
            var idx = closest.getAttribute('data-index');
            var se = sidebar.querySelector('[data-entry-index="' + idx + '"]');
            if (se) {
                se.classList.add('active');
                se.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }
    }
    var scrollTimer;
    scrollContainer.addEventListener('scroll', function() {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(syncSidebarHighlight, 50);
    });

    // --- Sidebar Filter Sync ---
    function syncSidebarFilters() {
        document.querySelectorAll('.sidebar-entry').forEach(function(se) {
            var idx = se.getAttribute('data-entry-index');
            if (idx === null) return;
            var entry = document.getElementById('entry-' + idx);
            if (!entry) return;
            var hidden = entry.classList.contains('filter-hidden') || entry.classList.contains('search-hidden');
            if (hidden) {
                se.classList.add('filter-hidden');
            } else {
                se.classList.remove('filter-hidden');
            }
        });
    }

    // --- Jump User Navigation ---
    function getUserEntries() {
        return Array.from(document.querySelectorAll('.main-container > .entry[data-type="user"]')).filter(function(e) {
            return !e.classList.contains('filter-hidden') && !e.classList.contains('search-hidden');
        });
    }
    var jumpPrev = document.getElementById('jump-prev');
    var jumpNext = document.getElementById('jump-next');
    if (jumpPrev) {
        jumpPrev.addEventListener('click', function() {
            var userEntries = getUserEntries();
            var scrollY = scrollContainer.scrollTop;
            for (var i = userEntries.length - 1; i >= 0; i--) {
                if (userEntries[i].offsetTop < scrollY - 10) {
                    userEntries[i].scrollIntoView({ block: 'start', behavior: 'smooth' });
                    return;
                }
            }
        });
    }
    if (jumpNext) {
        jumpNext.addEventListener('click', function() {
            var userEntries = getUserEntries();
            var scrollY = scrollContainer.scrollTop;
            for (var i = 0; i < userEntries.length; i++) {
                if (userEntries[i].offsetTop > scrollY + 60) {
                    userEntries[i].scrollIntoView({ block: 'start', behavior: 'smooth' });
                    return;
                }
            }
        });
    }

    // --- Diff Rendering ---
    document.querySelectorAll('pre[data-lang="diff"] code').forEach(function(codeEl) {
        var lines = codeEl.textContent.split('\n');
        codeEl.textContent = '';
        lines.forEach(function(line) {
            var span = document.createElement('span');
            span.className = 'diff-line';
            if (line.startsWith('+') && !line.startsWith('+++')) { span.classList.add('diff-add'); }
            else if (line.startsWith('-') && !line.startsWith('---')) { span.classList.add('diff-del'); }
            else if (line.startsWith('@@')) { span.classList.add('diff-hunk'); }
            span.textContent = line;
            codeEl.appendChild(span);
        });
    });

    // --- Syntax Highlighting ---
    var langKeywords = {
        'javascript': /\b(const|let|var|function|return|if|else|for|while|class|import|export|from|default|async|await|new|this|typeof|instanceof|try|catch|throw|finally|switch|case|break|continue|yield|of|in|do)\b/g,
        'typescript': /\b(const|let|var|function|return|if|else|for|while|class|import|export|from|default|async|await|new|this|typeof|instanceof|try|catch|throw|finally|switch|case|break|continue|yield|of|in|do|type|interface|enum|namespace|declare|abstract|implements|extends|as|keyof|readonly|public|private|protected|satisfies)\b/g,
        'python': /\b(def|class|return|if|elif|else|for|while|import|from|as|try|except|finally|raise|with|yield|lambda|pass|break|continue|and|or|not|in|is|True|False|None|self|async|await|global|nonlocal)\b/g,
        'rust': /\b(fn|let|mut|const|if|else|for|while|loop|match|struct|enum|impl|trait|pub|use|mod|crate|self|super|return|break|continue|where|async|await|move|ref|type|as|in|unsafe|extern|dyn|static|true|false)\b/g,
        'go': /\b(func|var|const|if|else|for|range|switch|case|return|break|continue|type|struct|interface|map|chan|go|defer|select|package|import|true|false|nil|default|fallthrough)\b/g,
        'bash': /\b(if|then|else|elif|fi|for|do|done|while|until|case|esac|function|return|local|export|source|echo|exit|set|unset|readonly|shift|trap|eval|exec|test|in)\b/g,
        'json': null,
        'sql': /\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AND|OR|NOT|IN|IS|NULL|AS|ORDER|BY|GROUP|HAVING|LIMIT|OFFSET|UNION|ALL|DISTINCT|SET|VALUES|INTO|TABLE|INDEX|VIEW|BEGIN|COMMIT|ROLLBACK|GRANT|REVOKE|PRIMARY|KEY|FOREIGN|REFERENCES|CASCADE|DEFAULT|CHECK|UNIQUE|CONSTRAINT|EXISTS|BETWEEN|LIKE|CASE|WHEN|THEN|ELSE|END|COUNT|SUM|AVG|MIN|MAX|COALESCE|CAST|TRUE|FALSE)\b/gi,
        'css': /\b(color|background|border|margin|padding|display|position|top|left|right|bottom|width|height|font|flex|grid|align|justify|overflow|opacity|transform|transition|animation|z-index|content|cursor|outline|box-sizing|text-align|vertical-align|white-space|min-width|max-width|min-height|max-height|gap|order|float|clear|visibility)\b/gi,
        'html': null,
    };
    langKeywords['js'] = langKeywords['javascript'];
    langKeywords['ts'] = langKeywords['typescript'];
    langKeywords['py'] = langKeywords['python'];
    langKeywords['rs'] = langKeywords['rust'];
    langKeywords['sh'] = langKeywords['bash'];
    langKeywords['shell'] = langKeywords['bash'];
    langKeywords['zsh'] = langKeywords['bash'];

    var stringRe = /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g;
    var numberRe = /\b(\d+\.?\d*(?:e[+-]?\d+)?|0x[0-9a-f]+|0b[01]+|0o[0-7]+)\b/gi;
    var singleLineComment = /(\/\/[^\n]*)/g;
    var hashComment = /(#[^\n]*)/g;
    var multiLineComment = /(\/\*[\s\S]*?\*\/)/g;
    var sqlComment = /(--[^\n]*)/g;

    function highlightCode(codeEl, lang) {
        if (!lang || lang === 'diff' || lang === 'json' || lang === 'html' || lang === 'xml') return;
        var text = codeEl.textContent;
        var tokens = [];
        var idx = 0;

        // Tokenize comments first
        var commentRes = [];
        if (lang === 'python' || lang === 'py' || lang === 'bash' || lang === 'sh' || lang === 'shell' || lang === 'zsh') {
            commentRes.push(hashComment);
        }
        if (lang === 'sql') {
            commentRes.push(sqlComment);
        }
        if (lang !== 'python' && lang !== 'py' && lang !== 'bash' && lang !== 'sh' && lang !== 'shell' && lang !== 'zsh' && lang !== 'sql' && lang !== 'css') {
            commentRes.push(singleLineComment);
            commentRes.push(multiLineComment);
        }
        if (lang === 'css') {
            commentRes.push(multiLineComment);
        }

        // Simple token-based approach: find all matches, sort by position, render
        var allMatches = [];
        function findAll(re, cls) {
            re.lastIndex = 0;
            var m;
            while ((m = re.exec(text)) !== null) {
                allMatches.push({ start: m.index, end: m.index + m[0].length, cls: cls, text: m[0] });
            }
        }
        commentRes.forEach(function(re) { findAll(re, 'syn-cmt'); });
        findAll(stringRe, 'syn-str');
        findAll(numberRe, 'syn-num');
        var kwRe = langKeywords[lang];
        if (kwRe) { findAll(kwRe, 'syn-kw'); }

        // Sort by start position, prioritize comments > strings > others
        var priority = { 'syn-cmt': 0, 'syn-str': 1, 'syn-num': 2, 'syn-kw': 3, 'syn-fn': 4, 'syn-type': 5, 'syn-op': 6 };
        allMatches.sort(function(a, b) { return a.start - b.start || (priority[a.cls] || 9) - (priority[b.cls] || 9); });

        // Remove overlapping matches
        var filtered = [];
        var lastEnd = 0;
        allMatches.forEach(function(m) {
            if (m.start >= lastEnd) {
                filtered.push(m);
                lastEnd = m.end;
            }
        });

        // Build HTML
        var html = '';
        var pos = 0;
        filtered.forEach(function(m) {
            if (m.start > pos) html += escapeHtmlJS(text.substring(pos, m.start));
            html += '<span class="' + m.cls + '">' + escapeHtmlJS(m.text) + '<\/span>';
            pos = m.end;
        });
        if (pos < text.length) html += escapeHtmlJS(text.substring(pos));
        codeEl.innerHTML = html;
    }

    function escapeHtmlJS(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    document.querySelectorAll('.md-code-block pre[data-lang]').forEach(function(pre) {
        var lang = pre.getAttribute('data-lang');
        var codeEl = pre.querySelector('code');
        if (codeEl && lang) highlightCode(codeEl, lang.toLowerCase());
    });

    // --- Permalink/Anchor ---
    if (location.hash) {
        var target = document.querySelector(location.hash);
        if (target && target.classList.contains('entry')) {
            target.classList.remove('collapsed');
            setTimeout(function() { target.scrollIntoView({ block: 'start' }); }, 100);
        }
    }
    document.querySelectorAll('.entry-time').forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            var href = link.getAttribute('href');
            history.replaceState(null, '', href);
        });
    });
})();
