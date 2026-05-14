/**
 * Log Doctor — dashboard plugin entry point (React component via SDK).
 *
 * Required interface:
 *   window.__HERMES_PLUGINS__.register('log-doctor', Component)
 *
 * Uses the Hermes Plugin SDK (window.__HERMES_PLUGIN_SDK__) which exposes:
 *   React, hooks (useState, useEffect), api, fetchJSON, components (Badge, Button, etc.)
 */
(function () {
  var SDK = window.__HERMES_PLUGIN_SDK__;
  var PLUGINS = window.__HERMES_PLUGINS__;

  if (!SDK || !PLUGINS) {
    console.error('[log-doctor] Plugin SDK not available. Dashboard may not be fully loaded.');
    return;
  }

  var React = SDK.React;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var fetchJSON = SDK.fetchJSON;
  var Badge = SDK.components.Badge;
  var Button = SDK.components.Button;

  var API_BASE = '/api/plugins/log-doctor';

  // Simple fetch wrapper with auth
  function apiGet(path) {
    return fetchJSON(API_BASE + path);
  }
  function apiPost(path, body) {
    return fetchJSON(API_BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
  }

  // -----------------------------------------------------------------------
  // Main component
  // -----------------------------------------------------------------------

  function LogDoctorApp() {
    var _ref1 = useState('active');
    var activeTab = _ref1[0], setActiveTab = _ref1[1];
    var _ref2 = useState([]);
    var errors = _ref2[0], setErrors = _ref2[1];
    var _ref3 = useState({});
    var stats = _ref3[0], setStats = _ref3[1];
    var _ref4 = useState({});
    var expanded = _ref4[0], setExpanded = _ref4[1];
    var _ref5 = useState(false);
    var loading = _ref5[0], setLoading = _ref5[1];
    var _ref6 = useState(null);
    var flashMsg = _ref6[0], setFlashMsg = _ref6[1];
    var _ref7 = useState({});
    var fixResults = _ref7[0], setFixResults = _ref7[1];

    if (!activeTab) { activeTab = 'active'; }
    if (!errors) { errors = []; }
    if (!stats) { stats = {}; }
    if (!expanded) { expanded = {}; }
    if (!fixResults) { fixResults = {}; }

    var _ref8 = useState('');
    var typeFilter = _ref8[0], setTypeFilter = _ref8[1];

    useEffect(function () {
      loadErrors(activeTab);
    }, [activeTab, typeFilter]);

    function loadErrors(tab) {
      setLoading(true);
      var query = '/errors?status=' + (tab === 'ignored' ? 'ignored' : tab === 'fixed' ? 'fixed' : 'active');
      if (typeFilter) { query += '&error_type=' + typeFilter; }
      apiGet(query)
        .then(function (data) {
          setErrors(data.errors || []);
          setStats(data.stats || {});
          setLoading(false);
        })
        .catch(function (e) {
          console.error('[log-doctor]', e);
          setLoading(false);
        });
    }

    function toggleExpand(id) {
      var next = {};
      for (var k in expanded) next[k] = expanded[k];
      next[id] = !expanded[id];
      setExpanded(next);
    }

    function doIgnore(id) {
      apiPost('/errors/' + id + '/ignore').then(function () {
        setFlashMsg({ text: 'Ignored', type: 'success' });
        loadErrors(activeTab);
      }).catch(function (e) { setFlashMsg({ text: e.message, type: 'error' }); });
    }

    function doUnignore(id) {
      apiPost('/errors/' + id + '/unignore').then(function () {
        setFlashMsg({ text: 'Un-ignored', type: 'success' });
        loadErrors(activeTab);
      }).catch(function (e) { setFlashMsg({ text: e.message, type: 'error' }); });
    }

    function doFix(id) {
      apiPost('/errors/' + id + '/fix').then(function (data) {
        var fr = {};
        for (var k in fixResults) fr[k] = fixResults[k];
        fr[id] = data;
        setFixResults(fr);
        if (data.ok) {
          setTimeout(function () { loadErrors(activeTab); }, 1500);
        }
      }).catch(function (e) { setFlashMsg({ text: e.message, type: 'error' }); });
    }
    function doScan() {
      setLoading(true);
      apiPost('/scan', { limit: 200 }).then(function (data) {
        setFlashMsg({ text: 'Scan complete: ' + data.total_errors + ' errors (' + data.new_errors + ' new)', type: 'success' });
        loadErrors(activeTab);
      }).catch(function (e) {
        setFlashMsg({ text: 'Scan failed: ' + e.message, type: 'error' });
        setLoading(false);
      });
    }
    function doAnalyze(id) {
      apiPost('/errors/' + id + '/analyze').then(function (data) {
        if (data.analysis_prompt) {
          navigator.clipboard.writeText(data.analysis_prompt).then(function () {
            setFlashMsg({ text: 'Analysis prompt copied! Paste to Hermes agent.', type: 'success' });
          });
        }
      }).catch(function (e) { setFlashMsg({ text: e.message, type: 'error' }); });
    }

    function tabClass(name) {
      return name === activeTab ? 'tab-btn active' : 'tab-btn';
    }

    var style = {
      container: { padding: '24px', color: '#c0caf5', fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif', background: '#1a1b26', minHeight: '100vh' },
      h1: { fontSize: '20px', marginBottom: '16px', color: '#7aa2f7' },
      tabBar: { display: 'flex', gap: '4px', marginBottom: '16px', borderBottom: '1px solid #414868', paddingBottom: '8px' },
      tabBtn: { padding: '6px 14px', border: 'none', background: 'none', color: '#565f89', cursor: 'pointer', fontSize: '14px', borderBottom: '2px solid transparent' },
      tabBtnActive: { padding: '6px 14px', border: 'none', background: 'none', color: '#7aa2f7', cursor: 'pointer', fontSize: '14px', borderBottom: '2px solid #7aa2f7', fontWeight: 'bold' },
      count: { marginLeft: '6px', fontSize: '12px', padding: '1px 8px', borderRadius: '10px', background: '#24283b', color: '#565f89' },
      errorList: { listStyle: 'none', padding: 0 },
      errorItem: { border: '1px solid #414868', borderRadius: '8px', marginBottom: '8px', background: '#24283b', overflow: 'hidden' },
      errorHeader: { display: 'flex', alignItems: 'center', padding: '12px 16px', cursor: 'pointer', gap: '12px' },
      typeBadge: function (t) { return { fontWeight: 'bold', fontSize: '11px', padding: '2px 8px', borderRadius: '4px', textTransform: 'uppercase', background: t === 'ERROR' || t === 'CRITICAL' ? 'rgba(247,118,142,0.2)' : 'rgba(224,175,104,0.2)', color: t === 'ERROR' || t === 'CRITICAL' ? '#f7768e' : '#e0af68' }; },
      msg: { flex: 1, fontSize: '14px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
      countBadge: { fontSize: '12px', color: '#565f89' },
      detail: { padding: '0 16px 16px', fontSize: '13px' },
      label: { color: '#565f89', fontSize: '11px', textTransform: 'uppercase', marginBottom: '2px' },
      value: { color: '#c0caf5', wordBreak: 'break-all', marginBottom: '8px' },
      pre: { background: '#1a1b26', padding: '8px 12px', borderRadius: '6px', fontFamily: 'monospace', fontSize: '12px', maxHeight: '200px', overflowY: 'auto', whiteSpace: 'pre-wrap', marginBottom: '8px' },
      actions: { display: 'flex', gap: '8px', marginTop: '12px' },
      btn: { padding: '6px 14px', border: '1px solid #414868', borderRadius: '6px', background: '#24283b', color: '#c0caf5', cursor: 'pointer', fontSize: '13px' },
      btnFix: { padding: '6px 14px', border: '1px solid #9ece6a', borderRadius: '6px', background: '#24283b', color: '#9ece6a', cursor: 'pointer', fontSize: '13px' },
      btnIgnore: { padding: '6px 14px', border: '1px solid #e0af68', borderRadius: '6px', background: '#24283b', color: '#e0af68', cursor: 'pointer', fontSize: '13px' },
      empty: { textAlign: 'center', padding: '40px', color: '#565f89' },
      flash: { position: 'fixed', top: '16px', right: '16px', padding: '12px 20px', borderRadius: '8px', fontSize: '13px', zIndex: 999, animation: 'fadeIn 0.3s' },
      flashSuccess: { position: 'fixed', top: '16px', right: '16px', padding: '12px 20px', borderRadius: '8px', fontSize: '13px', zIndex: 999, background: 'rgba(158,206,106,0.2)', color: '#9ece6a', border: '1px solid #9ece6a' },
      flashError: { position: 'fixed', top: '16px', right: '16px', padding: '12px 20px', borderRadius: '8px', fontSize: '13px', zIndex: 999, background: 'rgba(247,118,142,0.2)', color: '#f7768e', border: '1px solid #f7768e' },
      fixOk: { marginTop: '8px', padding: '8px 12px', borderRadius: '6px', fontSize: '12px', background: 'rgba(158,206,106,0.1)', border: '1px solid #9ece6a', color: '#9ece6a' },
      fixFail: { marginTop: '8px', padding: '8px 12px', borderRadius: '6px', fontSize: '12px', background: 'rgba(247,118,142,0.1)', border: '1px solid #f7768e', color: '#f7768e' },
    };

    // React.createElement wrapper
    var h = React.createElement;

    return h('div', { style: style.container },
      h('h1', { style: style.h1 }, '\uD83E\uDE7A Log Doctor'),

      flashMsg && h('div', { style: flashMsg.type === 'error' ? style.flashError : style.flashSuccess, onClick: function () { setFlashMsg(null); } }, flashMsg.text),

      h('div', { style: { display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' } },
        h('button', { style: { padding: '8px 18px', border: '1px solid #7aa2f7', borderRadius: '6px', background: 'rgba(122,162,247,0.1)', color: '#7aa2f7', cursor: 'pointer', fontSize: '14px', fontWeight: 'bold' }, onClick: function () { doScan(); } }, '\u{1F50D} Scan Now'),
        stats.last_scan && h('span', { style: { fontSize: '12px', color: '#565f89' } },
          'Last scan: ' + stats.last_scan.scanned_at + ' \u00B7 ' + stats.last_scan.total_errors + ' errors (' + stats.last_scan.new_errors + ' new, ' + stats.last_scan.ignored_skipped + ' skipped)')
      ),

      h('div', { style: style.tabBar },
        h('button', { style: activeTab === 'active' ? style.tabBtnActive : style.tabBtn, onClick: function () { setActiveTab('active'); } },
          'Active ', h('span', { style: style.count }, stats.active || 0)),
        h('button', { style: activeTab === 'ignored' ? style.tabBtnActive : style.tabBtn, onClick: function () { setActiveTab('ignored'); } },
          'Ignored ', h('span', { style: style.count }, stats.ignored || 0)),
        h('button', { style: activeTab === 'fixed' ? style.tabBtnActive : style.tabBtn, onClick: function () { setActiveTab('fixed'); } },
          'Fixed ', h('span', { style: style.count }, stats.fixed || 0))
      ),

      h('div', { style: { display: 'flex', gap: '4px', marginBottom: '12px' } },
        ['All', 'WARNING', 'ERROR', 'CRITICAL'].map(function (t) {
          var isActive = typeFilter === (t === 'All' ? '' : t);
          return h('button', {
            key: t,
            style: {
              padding: '4px 12px', border: '1px solid #414868', borderRadius: '4px',
              background: isActive ? 'rgba(122,162,247,0.15)' : 'transparent',
              color: isActive ? '#7aa2f7' : '#565f89', cursor: 'pointer', fontSize: '12px'
            },
            onClick: function () { setTypeFilter(t === 'All' ? '' : t); }
          }, t);
        })
      ),

      loading ? h('div', { style: style.empty }, 'Loading...') :
      errors.length === 0 ? h('div', { style: style.empty }, 'No ' + activeTab + ' errors. \uD83C\uDF89') :
      h('ul', { style: style.errorList },
        errors.map(function (e) {
          var isExpanded = !!expanded[e.id];
          var fr = fixResults[e.id];
          return h('li', { key: e.id, style: style.errorItem },
            h('div', { style: style.errorHeader, onClick: function () { toggleExpand(e.id); } },
              h('span', { style: { fontSize: '12px', color: '#565f89', transition: 'transform 0.2s', transform: isExpanded ? 'rotate(90deg)' : 'none' } }, '\u25B6'),
              h('span', { style: style.typeBadge(e.error_type) }, e.error_type),
              h('span', { style: style.msg }, e.message),
              h('span', { style: style.countBadge }, '\u00D7' + e.count)
            ),
            isExpanded && h('div', { style: style.detail },
              h('div', { style: style.label }, 'First Seen'), h('div', { style: style.value }, e.first_seen),
              h('div', { style: style.label }, 'Last Seen'), h('div', { style: style.value }, e.last_seen),
              e.file_path && h('div', {}, h('div', { style: style.label }, 'File'), h('div', { style: style.value }, e.file_path + (e.line_number ? ':' + e.line_number : ''))),
              e.context && h('div', {}, h('div', { style: style.label }, 'Raw Log'), h('pre', { style: style.pre }, e.context)),
              e.fix_description && h('div', {}, h('div', { style: style.label }, 'Fix Suggestion'), h('div', { style: style.value }, e.fix_description)),
              e.fix_command && h('div', {}, h('div', { style: style.label }, 'Fix Command'), h('pre', { style: style.pre }, e.fix_command)),
              h('div', { style: style.actions },
                e.status === 'active' && h('button', { style: style.btn, onClick: function (ev) { ev.stopPropagation(); doAnalyze(e.id); } }, 'Ask Agent'),
                e.status === 'active' && h('button', { style: style.btnIgnore, onClick: function (ev) { ev.stopPropagation(); doIgnore(e.id); } }, 'Ignore'),
                e.status === 'ignored' && h('button', { style: style.btn, onClick: function (ev) { ev.stopPropagation(); doUnignore(e.id); } }, 'Un-ignore'),
                e.fix_command && e.status === 'active' && h('button', { style: style.btnFix, onClick: function (ev) { ev.stopPropagation(); doFix(e.id); } }, 'Apply Fix')
              ),
              fr && fr.ok && h('div', { style: style.fixOk }, 'Fix applied! Exit code: ' + fr.result.exit_code),
              fr && !fr.ok && h('div', { style: style.fixFail }, fr.error || 'Fix failed')
            )
          );
        })
      )
    );
  }

  // Register with the dashboard
  PLUGINS.register('log-doctor', LogDoctorApp);
  console.log('[log-doctor] Plugin registered successfully.');
})();
