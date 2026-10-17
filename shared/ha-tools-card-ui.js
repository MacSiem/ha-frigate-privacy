// Shared card presentation. No data access, state mutations or permissions.
function createCardUi() {
  const css = `
:host{--ht-action-bg:#2563eb;--ht-action-text:#fff;--ht-focus:#2563eb;display:block;max-width:1200px;margin-inline:auto;color-scheme:light}
:host(.bento-dark){--ht-action-bg:#4f46e5;--ht-action-text:#fff;--ht-focus:#a5b4fc;color-scheme:dark}
.card{width:100%;max-width:1200px;font-size:14px}
.card p,.card input,.card select,.card textarea,.card button{font-size:14px}
.card .helper{font-size:14px}
.card .channel-badge,.card .phase,.card .camera-countdown,.card .subtitle{font-size:12px;letter-spacing:normal}
.card .btn-primary{background:var(--ht-action-bg);color:var(--ht-action-text);border-color:var(--ht-action-bg)}
.card .btn-primary:hover{filter:brightness(.9)}
.card .btn-primary:disabled{opacity:1;filter:none;background:var(--fp-soft);color:var(--fp-muted);border-color:var(--fp-border);cursor:not-allowed}
.card .btn-danger{background:transparent;color:#b42318;border:1px solid #b42318}
:host(.bento-dark) .card .btn-danger{background:transparent;color:#ffb4ab;border-color:#ffb4ab}
.card :is(button,input,select,textarea,a,summary,[role="button"]):focus-visible{outline:3px solid var(--ht-focus);outline-offset:2px}
.card .tabs{display:flex;flex-wrap:nowrap;overflow-x:auto;gap:4px;scrollbar-width:thin;overscroll-behavior-inline:contain;max-width:100%;padding:4px}
.card .tab-btn{flex:0 0 auto;white-space:nowrap;overflow-wrap:normal;min-height:44px}
.card input,.card select,.card textarea{background:var(--fp-card);color:var(--fp-text);accent-color:var(--ht-action-bg)}
.card .seg-item{flex:1 1 auto;padding:10px 8px;white-space:nowrap;overflow-wrap:normal}
.camera-quick-actions,.duration-presets{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-block:10px}
.camera-quick-actions .btn{padding:8px 12px;min-height:44px}
.duration-label{display:flex;align-items:center;gap:8px;min-width:0;font-size:14px}
.duration-label input{width:90px;min-width:64px}
.card .duration-row{display:flex;align-items:center;flex-wrap:wrap;gap:12px}
.card .intro-banner{padding:8px 12px;margin-bottom:12px}
.card .intro-banner summary,.notification-help summary{min-height:44px;cursor:pointer;display:list-item;list-style-position:inside}
.card .camera-grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr))}
.card .camera-name{font-size:14px;overflow-wrap:break-word}
.card dialog{max-width:min(480px,calc(100% - 32px));box-sizing:border-box;border:1px solid var(--fp-border);border-radius:16px;background:var(--fp-card);color:var(--fp-text);padding:20px}
.card dialog::backdrop{background:rgba(0,0,0,.5)}
.card.compact .header{padding:16px}.card.compact .body{padding:12px}.card.compact .subtitle{display:none}
@container(max-width:500px){.card .brand-mark{display:none}.card .header{gap:8px}.card .body,.card .header{padding:12px}.card .status-pill{margin-left:0}.card .camera-grid{grid-template-columns:minmax(0,1fr)}}
`;
  return {css};
}
// Node tests use the canonical factory;
if (typeof module !== 'undefined') module.exports = {createCardUi};
