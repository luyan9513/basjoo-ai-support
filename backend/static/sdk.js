"use strict";(()=>{var j=/\[([^\]]+)\]\((#source-(\d+)|https?:\/\/[^\s)]+)\)/g;function x(r){return r.type==="url"&&typeof r.url=="string"&&/^https?:\/\//.test(r.url)}function y(r){if(x(r))return{type:"url",title:r.title?.trim()||r.url,url:r.url,...r.snippet?.trim()?{snippet:r.snippet.trim()}:{}};if(r.type!=="file")return null;let e=r.filename?.trim(),t=e||r.title?.trim();return t?{type:"file",title:t,...e?{filename:e}:{},...r.snippet?.trim()?{snippet:r.snippet.trim()}:{},...r.doc_id?.trim()?{docId:r.doc_id.trim()}:{}}:null}function S(r){return r.type==="url"?`url:${r.url}`:`file:${r.docId||r.filename||r.title}`}function w(r,e=[]){if(!r)return{content:r,references:[]};let t=[],i=new Set,n=new Set;for(let o of e){x(o)&&n.add(o.url);let a=y(o);if(!a)continue;let c=S(a);i.has(c)||(i.add(c),t.push(a))}return{content:r.replace(j,(o,a,c,l)=>l||n.has(c)?a:o),references:t}}var p={agentId:["agentId","agent_id"],apiBase:["apiBase","api_base"],themeColor:["themeColor","theme_color"],welcomeMessage:["welcomeMessage","welcome_message"],language:["language","locale"],position:["position"],theme:["theme"]};function k(r){if(!r)return"/basjoo-logo.png";try{return new URL("/basjoo-logo.png",`${r}/`).toString()}catch{return"/basjoo-logo.png"}}var v=class{constructor(){this.memoryStore=new Map;this.storageAvailable=null}isAvailable(){if(this.storageAvailable!==null)return this.storageAvailable;try{let e="__storage_test__";return window.localStorage.setItem(e,"test"),window.localStorage.removeItem(e),this.storageAvailable=!0,!0}catch{return this.storageAvailable=!1,!1}}getItem(e){if(this.isAvailable())try{return window.localStorage.getItem(e)}catch{}return this.memoryStore.get(e)??null}setItem(e,t){if(this.isAvailable())try{window.localStorage.setItem(e,t);return}catch{}this.memoryStore.set(e,t)}removeItem(e){if(this.isAvailable())try{window.localStorage.removeItem(e);return}catch{}this.memoryStore.delete(e)}},b=class{constructor(e){this.container=null;this.button=null;this.unreadBadge=null;this.chatWindow=null;this.messages=[];this.sessionId=null;this.visitorToken=null;this.isOpen=!1;this.VISITOR_STORAGE_KEY="basjoo_visitor_id";this.effectiveTheme="light";this.originalTitle="";this.titleBlinkInterval=null;this.hasUnread=!1;this.pollIntervalId=null;this.lastMessageId=0;this.isSending=!1;this.handoffRequested=!1;this.isRequestingHandoff=!1;this.streamAbortController=null;this.streamingMessage=null;this.streamingMessageContent=null;this.thinkingIndicator=null;this.thinkingIndicatorText=null;this.thinkingElapsed=0;this.thinkingTimerId=null;this.currentStreamContent="";this.currentStreamSources=[];this._buttonClickListener=null;this._closeBtnClickListener=null;this._sendBtnClickListener=null;this._inputKeypressListener=null;this._handoffClickListener=null;let t=this.detectApiBase(e.apiBase);this.hasTitleOverride=typeof e.title=="string"&&e.title.trim().length>0,this.hasWelcomeMessageOverride=typeof e.welcomeMessage=="string"&&e.welcomeMessage.trim().length>0,this.config={agentId:e.agentId,apiBase:t,themeColor:e.themeColor||"",logoUrl:e.logoUrl||k(t),title:e.title||"AI\u52A9\u624B",welcomeMessage:e.welcomeMessage||"\u4F60\u597D\uFF01\u6709\u4EC0\u4E48\u53EF\u4EE5\u5E2E\u52A9\u60A8\u7684\u5417\uFF1F",language:e.language||"auto",position:e.position||"right",theme:e.theme||"auto"},this.STORAGE_KEY=`basjoo_session_${this.config.agentId}`,this.VISITOR_TOKEN_STORAGE_KEY=`basjoo_visitor_token_${this.config.agentId}`,this.storage=new v,this.sessionId=this.storage.getItem(this.STORAGE_KEY),this.visitorToken=this.storage.getItem(this.VISITOR_TOKEN_STORAGE_KEY),this.visitorId=this.storage.getItem(this.VISITOR_STORAGE_KEY)||this.generateVisitorId(),this.effectiveTheme=this.getEffectiveTheme()}generateVisitorId(){let e=`visitor_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,11)}`;return this.storage.setItem(this.VISITOR_STORAGE_KEY,e),e}getVisitorAuthHeaders(){return this.visitorToken?{Authorization:`Bearer ${this.visitorToken}`}:{}}clearStoredSession(){this.sessionId=null,this.visitorToken=null,this.storage.removeItem(this.STORAGE_KEY),this.storage.removeItem(this.VISITOR_TOKEN_STORAGE_KEY),this.stopPolling(),this.updateHandoffButton()}detectApiBase(e){if(e)try{let s=new URL(e,window.location.href);if((s.protocol==="http:"||s.protocol==="https:")&&s.port==="3000"){let o=`${s.protocol}//${s.hostname}:8000`;return console.info("[Basjoo Widget] Rewriting configured dev apiBase to direct backend:",o),o}return s.toString().replace(/\/$/,"")}catch{return e}let t=document.currentScript;if(t instanceof HTMLScriptElement&&t.src)try{let s=new URL(t.src,window.location.href);return console.info("[Basjoo Widget] Detected API base from current script:",s.origin),s.origin}catch{}let i=document.querySelectorAll("script[src]");for(let s of i){let o=s.getAttribute("src")||"";if(!(!o.includes("sdk.js")&&!o.includes("basjoo")))try{let a=new URL(o,window.location.href);return console.info("[Basjoo Widget] Detected API base from script src:",a.origin),a.origin}catch{}}let n=window.location.port;if(n==="3000"||n==="5173"){let s=`${window.location.protocol}//${window.location.hostname}:8000`;return console.info("[Basjoo Widget] Development mode detected, using:",s),s}return window.location.protocol==="file:"?(console.error("[Basjoo Widget] Cannot determine API base from a local file. Please set apiBase explicitly."),""):(console.warn("[Basjoo Widget] Falling back to window.location.origin. Set apiBase explicitly if the API is hosted elsewhere."),window.location.origin)}getEffectiveTheme(){return this.config.theme==="light"||this.config.theme==="dark"?this.config.theme:typeof window<"u"&&window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}async loadPublicConfig(){if(!this.config.apiBase){console.warn("[Basjoo Widget] Skipping public config fetch because apiBase could not be determined.");return}try{let e=new URL(`${this.config.apiBase}/api/v1/config:public`);this.config.agentId&&e.searchParams.set("agent_id",this.config.agentId);let t=await fetch(e.toString());if(!t.ok)throw new Error(`HTTP ${t.status}: ${t.statusText}`);let i=await t.json();!this.config.agentId&&i.default_agent_id&&(this.config.agentId=i.default_agent_id),this.config.themeColor=this.config.themeColor||i.widget_color||"#3B82F6",this.hasTitleOverride||(this.config.title=i.widget_title||"AI\u52A9\u624B"),this.hasWelcomeMessageOverride||(this.config.welcomeMessage=i.welcome_message||"\u4F60\u597D\uFF01\u6709\u4EC0\u4E48\u53EF\u4EE5\u5E2E\u52A9\u60A8\u7684\u5417\uFF1F"),this.effectiveTheme=this.getEffectiveTheme()}catch(e){console.warn("[Basjoo Widget] Failed to load public config, using defaults.",e),e instanceof TypeError&&console.warn("[Basjoo Widget] Public config request may be blocked by CORS, network issues, or an incorrect apiBase:",this.config.apiBase)}}async init(){if(!document.body){console.warn("[Basjoo Widget] document.body is not available yet. Call init() after DOMContentLoaded or place the embed code near the end of <body>.");return}if(document.getElementById("basjoo-widget-container")){console.warn("[Basjoo Widget] Initialization skipped because #basjoo-widget-container already exists. Avoid loading or initializing the widget twice on the same page.");return}if(await this.loadPublicConfig(),this.originalTitle=document.title,this.createStyles(),this.createContainer(),this.createButton(),this.createChatWindow(),this.showGreetingBubble(),this.startTitleBlink(),this.sessionId&&this.visitorToken){this.loadHistory();return}(this.sessionId||this.visitorToken)&&this.clearStoredSession(),this.config.welcomeMessage&&this.addMessage({role:"assistant",content:this.config.welcomeMessage,timestamp:new Date})}showGreetingBubble(){if(!this.button)return;let e=document.createElement("div");e.className="basjoo-greeting-bubble",e.textContent=this.getText("greetingBubble");let t=this.config.position;e.style.position="fixed",e.style.bottom="100px",e.style[t]="24px",e.style.zIndex="9999",document.body.appendChild(e),setTimeout(()=>{e.remove()},5e3)}async loadHistory(){if(this.sessionId){try{let e=await fetch(`${this.config.apiBase}/api/v1/chat/messages?session_id=${encodeURIComponent(this.sessionId)}`,{headers:this.getVisitorAuthHeaders()});if(!e.ok)throw new Error("Failed to load history");let t=await e.json();if(t&&t.length>0){for(let i of t)this.addMessage({role:i.role==="user"?"user":"assistant",content:i.content,sources:i.sources,timestamp:new Date}),i.id>this.lastMessageId&&(this.lastMessageId=i.id);this.startPolling();return}}catch{}this.clearStoredSession(),this.config.welcomeMessage&&this.addMessage({role:"assistant",content:this.config.welcomeMessage,timestamp:new Date})}}startTitleBlink(){if(this.titleBlinkInterval)return;this.hasUnread=!0,this.updateUnreadBadge();let e=!0;this.titleBlinkInterval=window.setInterval(()=>{document.title=e?this.originalTitle:"\u2757 "+this.getText("newMessage"),e=!e},1e3)}stopTitleBlink(){this.titleBlinkInterval&&(clearInterval(this.titleBlinkInterval),this.titleBlinkInterval=null),document.title=this.originalTitle,this.hasUnread=!1,this.updateUnreadBadge()}createStyles(){let e=document.createElement("style");e.id="basjoo-widget-styles";let t=this.effectiveTheme==="dark",i=t?"#1a1a2e":"white",n=t?"#e2e8f0":"#1f2937",s=t?"#94a3b8":"#6b7280",o=t?"rgba(148, 163, 184, 0.2)":"#e5e7eb",a=t?"#0f0f1a":"white",c=t?"#2d2d44":"#f3f4f6",l=t?"rgba(239, 68, 68, 0.2)":"#fef2f2";e.textContent=`
      #basjoo-widget-container, #basjoo-widget-container * {
        box-sizing: border-box;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      }

      #basjoo-widget-button {
        position: fixed;
        bottom: 24px;
        ${this.config.position==="left"?"left":"right"}: 24px;
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background-color: ${this.config.themeColor};
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s, box-shadow 0.2s;
        z-index: 9999;
      }

      #basjoo-widget-button:hover {
        transform: scale(1.05);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
      }

      #basjoo-widget-button svg {
        width: 30px;
        height: 30px;
        fill: white;
      }

      .basjoo-unread-badge {
        position: absolute;
        top: -4px;
        right: -4px;
        min-width: 20px;
        height: 20px;
        padding: 0 6px;
        border-radius: 10px;
        background: #ef4444;
        color: white;
        font-size: 11px;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px solid white;
      }

      .basjoo-greeting-bubble {
        background: white;
        color: ${n};
        padding: 10px 14px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        font-size: 13px;
        line-height: 1.4;
        animation: basjoo-bubble-fadein 0.3s ease-out;
        max-width: 200px;
      }

      .basjoo-greeting-bubble::after {
        content: '';
        position: absolute;
        bottom: -6px;
        ${this.config.position==="left"?"left":"right"}: 30px;
        width: 12px;
        height: 12px;
        background: white;
        transform: rotate(45deg);
        border-bottom: 1px solid ${o};
        border-right: 1px solid ${o};
      }

      @keyframes basjoo-bubble-fadein {
        from {
          opacity: 0;
          transform: translateY(10px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      #basjoo-chat-window {
        position: fixed;
        bottom: 96px;
        ${this.config.position==="left"?"left":"right"}: 24px;
        width: 380px;
        height: 600px;
        max-height: calc(100vh - 120px);
        background: ${i};
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
        display: flex;
        flex-direction: column;
        overflow: hidden;
        transform: scale(0);
        transform-origin: ${this.config.position==="left"?"bottom left":"bottom right"};
        transition: transform 0.3s ease;
        z-index: 9998;
      }

      #basjoo-chat-window.open {
        transform: scale(1);
      }

      #basjoo-chat-window.closing {
        transform: scale(0);
      }

      .basjoo-header {
        background: linear-gradient(135deg, ${this.config.themeColor} 0%, ${this.adjustColor(this.config.themeColor,-20)} 100%);
        color: white;
        padding: 20px 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-shrink: 0;
      }

      .basjoo-header-title {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 18px;
        font-weight: 600;
      }

      .basjoo-header-logo {
        width: 32px;
        height: 32px;
        object-fit: contain;
        border-radius: 8px;
        background: rgba(255,255,255,0.2);
        padding: 4px;
        flex-shrink: 0;
      }

      .basjoo-close {
        width: 32px;
        height: 32px;
        border: none;
        background: rgba(255,255,255,0.15);
        border-radius: 8px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s;
        color: white;
      }

      .basjoo-close:hover {
        background: rgba(255,255,255,0.25);
      }

      .basjoo-messages {
        flex: 1;
        overflow-y: auto;
        padding: 20px;
        display: flex;
        flex-direction: column;
        gap: 16px;
        background: ${a};
      }

      #basjoo-widget-container .basjoo-message {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        max-width: 85%;
        min-width: 0;
        width: fit-content;
        animation: basjoo-message-fadein 0.3s ease-out;
      }

      #basjoo-widget-container .basjoo-message-user {
        align-self: flex-end;
        align-items: flex-end;
      }

      #basjoo-widget-container .basjoo-message-assistant {
        align-self: flex-start;
        align-items: flex-start;
      }

      #basjoo-widget-container .basjoo-message-content {
        display: block;
        align-self: flex-start;
        width: fit-content;
        max-width: 100%;
        min-width: 0;
        padding: 12px 16px;
        border-radius: 16px;
        font-size: 14px;
        line-height: 1.6;
        white-space: pre-wrap;
        word-break: break-word;
        overflow-wrap: anywhere;
      }

      #basjoo-widget-container .basjoo-message-user .basjoo-message-content {
        align-self: flex-end;
      }

      #basjoo-widget-container .basjoo-message-content > * {
        display: block;
        max-width: 100%;
      }

      #basjoo-widget-container .basjoo-message-content p,
      #basjoo-widget-container .basjoo-message-content ul,
      #basjoo-widget-container .basjoo-message-content ol,
      #basjoo-widget-container .basjoo-message-content pre,
      #basjoo-widget-container .basjoo-message-content blockquote {
        margin: 0 0 10px;
      }

      #basjoo-widget-container .basjoo-message-content p:last-child,
      #basjoo-widget-container .basjoo-message-content ul:last-child,
      #basjoo-widget-container .basjoo-message-content ol:last-child,
      #basjoo-widget-container .basjoo-message-content pre:last-child,
      #basjoo-widget-container .basjoo-message-content blockquote:last-child {
        margin-bottom: 0;
      }

      #basjoo-widget-container .basjoo-message-content ul,
      #basjoo-widget-container .basjoo-message-content ol {
        padding-left: 18px;
      }

      #basjoo-widget-container .basjoo-message-content code {
        font-family: SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace;
        font-size: 12px;
        background: rgba(15, 23, 42, 0.08);
        padding: 1px 4px;
        border-radius: 4px;
      }

      #basjoo-widget-container .basjoo-message-content pre {
        background: #0f172a;
        color: #e2e8f0;
        padding: 10px 12px;
        border-radius: 10px;
        overflow-x: auto;
      }

      #basjoo-widget-container .basjoo-message-content pre code {
        background: transparent;
        padding: 0;
        color: inherit;
      }

      #basjoo-widget-container .basjoo-message-content a {
        color: ${this.adjustColor(this.config.themeColor,-10)};
        text-decoration: underline;
      }

      #basjoo-widget-container .basjoo-message-content blockquote {
        padding-left: 12px;
        border-left: 3px solid rgba(148, 163, 184, 0.4);
        color: ${s};
      }

      #basjoo-widget-container .basjoo-message-user .basjoo-message-content {
        background: ${this.config.themeColor};
        color: white;
        border-bottom-right-radius: 4px;
      }

      #basjoo-widget-container .basjoo-message-user .basjoo-message-content a {
        color: white;
      }

      #basjoo-widget-container .basjoo-message-user .basjoo-message-content code {
        background: rgba(255, 255, 255, 0.18);
        color: white;
      }

      #basjoo-widget-container .basjoo-message-assistant .basjoo-message-content {
        background: ${c};
        color: ${n};
        border-bottom-left-radius: 4px;
      }

      #basjoo-widget-container .basjoo-references {
        margin-top: 12px;
        padding-top: 10px;
        border-top: 1px solid ${o};
      }

      #basjoo-widget-container .basjoo-references-title {
        margin-bottom: 8px;
        color: ${s};
        font-size: 12px;
        font-weight: 600;
      }

      #basjoo-widget-container .basjoo-reference-card {
        display: block;
        padding: 8px 10px;
        border: 1px solid ${o};
        border-radius: 8px;
        background: ${a};
        color: ${n};
        text-decoration: none;
      }

      #basjoo-widget-container .basjoo-reference-card + .basjoo-reference-card {
        margin-top: 6px;
      }

      #basjoo-widget-container .basjoo-reference-name {
        font-size: 12px;
        font-weight: 600;
        word-break: break-word;
      }

      #basjoo-widget-container .basjoo-reference-snippet {
        margin-top: 4px;
        color: ${s};
        font-size: 11px;
        line-height: 1.45;
        display: -webkit-box;
        overflow: hidden;
        -webkit-box-orient: vertical;
        -webkit-line-clamp: 2;
      }

      #basjoo-widget-container .basjoo-message-error .basjoo-message-content {
        background: ${l};
        color: ${t?"#fca5a5":"#dc2626"};
        border: 1px solid ${t?"rgba(239,68,68,0.35)":"#fecaca"};
      }

      .basjoo-stream-cursor {
        display: inline-block;
        width: 0.5rem;
        height: 1em;
        margin-left: 0.12rem;
        vertical-align: text-bottom;
        background: ${this.config.themeColor};
        animation: basjoo-cursor-blink 1s steps(1) infinite;
      }

      @keyframes basjoo-cursor-blink {
        0%, 50% { opacity: 1; }
        50.01%, 100% { opacity: 0; }
      }

      .basjoo-loading {
        display: flex;
        gap: 4px;
        padding: 12px 16px !important;
        align-self: flex-start;
        margin-top: 4px !important;
      }

      .basjoo-loading-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: ${s};
        animation: basjoo-bounce 1.4s infinite ease-in-out both;
      }

      .basjoo-loading-dot:nth-child(1) { animation-delay: -0.32s; }
      .basjoo-loading-dot:nth-child(2) { animation-delay: -0.16s; }

      @keyframes basjoo-bounce {
        0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
        40% { transform: scale(1); opacity: 1; }
      }

      .basjoo-input-area {
        padding: 16px 20px 24px 20px !important;
        border-top: 1px solid ${o};
        display: flex;
        gap: 12px;
        background: ${i};
        flex-shrink: 0;
      }

      .basjoo-handoff {
        min-width: 64px;
        height: 40px;
        margin: 4px 0 8px;
        padding: 0 10px;
        border: 1px solid ${this.config.themeColor};
        border-radius: 20px;
        background: transparent;
        color: ${this.config.themeColor};
        cursor: pointer;
        font-size: 12px;
        font-weight: 600;
        flex-shrink: 0;
      }

      .basjoo-handoff:hover:not(:disabled) {
        background: ${this.hexToRgba(this.config.themeColor,.1)};
      }

      .basjoo-handoff:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      .basjoo-input {
        flex: 1;
        height: 48px;
        padding: 0 20px 0 20px !important;
        border: 1px solid ${o};
        border-radius: 24px;
        font-size: 14px;
        outline: none;
        transition: all 0.2s;
        background: ${a};
        color: ${n};
        margin-bottom: 8px !important;
        margin-left: 4px !important;
      }

      .basjoo-input::placeholder {
        color: ${s};
      }

      .basjoo-input:focus {
        border-color: ${this.config.themeColor};
        box-shadow: 0 0 0 3px ${this.hexToRgba(this.config.themeColor,.1)};
      }

      .basjoo-send {
        width: 48px;
        height: 48px;
        border: none;
        border-radius: 50%;
        background: ${this.config.themeColor};
        color: white;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s;
        flex-shrink: 0;
      }

      .basjoo-send:hover:not(:disabled) {
        transform: scale(1.05);
        box-shadow: 0 4px 12px ${this.hexToRgba(this.config.themeColor,.3)};
      }

      .basjoo-send:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      .basjoo-send svg {
        width: 20px;
        height: 20px;
        stroke: currentColor;
      }

      .basjoo-error {
        padding: 12px 16px;
        background: ${l};
        color: ${t?"#fca5a5":"#dc2626"};
        font-size: 13px;
        text-align: center;
        border-top: 1px solid ${t?"rgba(239,68,68,0.35)":"#fecaca"};
      }

      #basjoo-widget-container .basjoo-message-time {
        font-size: 11px;
        color: ${s};
        margin-top: 4px;
        padding: 0 4px;
      }

      #basjoo-widget-container .basjoo-message-user .basjoo-message-time {
        text-align: right;
      }

      .basjoo-thinking {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: ${s};
        font-size: 12px;
        margin-top: 8px;
      }

      .basjoo-thinking-spinner {
        width: 12px;
        height: 12px;
        border: 2px solid ${this.hexToRgba(this.config.themeColor,.2)};
        border-top-color: ${this.config.themeColor};
        border-radius: 50%;
        animation: basjoo-spin 0.8s linear infinite;
      }

      @keyframes basjoo-spin {
        to { transform: rotate(360deg); }
      }

      @keyframes basjoo-message-fadein {
        from {
          opacity: 0;
          transform: translateY(10px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      @media (max-width: 480px) {
        #basjoo-chat-window {
          width: calc(100vw - 32px);
          height: calc(100vh - 120px);
          max-height: 640px;
          bottom: 88px;
          left: 16px !important;
          right: 16px !important;
        }

        #basjoo-widget-button {
          bottom: 16px;
          ${this.config.position==="left"?"left":"right"}: 16px;
        }
      }
    `,document.head.appendChild(e)}adjustColor(e,t){let i=!1,n=e;n[0]==="#"&&(n=n.slice(1),i=!0);let s=parseInt(n,16),o=(s>>16)+t,a=(s>>8&255)+t,c=(s&255)+t;return o=Math.max(0,Math.min(255,o)),a=Math.max(0,Math.min(255,a)),c=Math.max(0,Math.min(255,c)),`${i?"#":""}${(o<<16|a<<8|c).toString(16).padStart(6,"0")}`}hexToRgba(e,t){let i=e.replace("#","");if(i.length===3){let[c,l,g]=i.split("");i=`${c}${c}${l}${l}${g}${g}`}let n=parseInt(i,16),s=n>>16&255,o=n>>8&255,a=n&255;return`rgba(${s}, ${o}, ${a}, ${t})`}updateUnreadBadge(){if(this.button){if(this.hasUnread){if(!this.unreadBadge){let e=document.createElement("span");e.className="basjoo-unread-badge",e.textContent="1",this.button.appendChild(e),this.unreadBadge=e}return}this.unreadBadge?.remove(),this.unreadBadge=null}}createContainer(){this.container=document.createElement("div"),this.container.id="basjoo-widget-container",document.body.appendChild(this.container)}createButton(){this.button=document.createElement("div"),this.button.id="basjoo-widget-button",this.button.innerHTML=`
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
      </svg>
    `,this._buttonClickListener=()=>this.toggle(),this.button.addEventListener("click",this._buttonClickListener),this.container.appendChild(this.button),this.updateUnreadBadge()}createChatWindow(){this.chatWindow=document.createElement("div"),this.chatWindow.id="basjoo-chat-window";let e=this.config.logoUrl?this.sanitizeUrlAttribute(this.config.logoUrl):"",t=this.escapeHtml(this.config.title),i=this.escapeHtml(this.getText("inputPlaceholder")),n=this.escapeHtml(this.getText("handoffButton"));this.chatWindow.innerHTML=`
      <div class="basjoo-header">
        <div class="basjoo-header-title">
          ${e?`<img src="${e}" class="basjoo-header-logo" alt="">`:""}
          <span>${t}</span>
        </div>
        <button class="basjoo-close">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="basjoo-messages"></div>
      <div class="basjoo-input-area">
        <button type="button" class="basjoo-handoff" disabled>${n}</button>
        <input type="text" class="basjoo-input" placeholder="${i}" maxlength="2000">
        <button class="basjoo-send">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        </button>
      </div>
    `;let s=this.chatWindow.querySelector(".basjoo-close");this._closeBtnClickListener=()=>this.close(),s.addEventListener("click",this._closeBtnClickListener);let o=this.chatWindow.querySelector(".basjoo-input"),a=this.chatWindow.querySelector(".basjoo-send"),c=this.chatWindow.querySelector(".basjoo-handoff");this._handoffClickListener=()=>{this.requestHumanHandoff()},c.addEventListener("click",this._handoffClickListener),this.updateHandoffButton(),this._sendBtnClickListener=()=>{if(this.isSending)return;let l=o.value.trim();if(l){if(l.length>2e3){this.showError(this.getText("messageTooLong"));return}this.sendMessage(l),o.value=""}},a.addEventListener("click",this._sendBtnClickListener),this._inputKeypressListener=l=>{l.key==="Enter"&&this._sendBtnClickListener?.()},o.addEventListener("keypress",this._inputKeypressListener),this.container.appendChild(this.chatWindow)}toggle(){if(this.isOpen){this.close();return}this.open()}open(){this.isOpen=!0,this.chatWindow?.classList.remove("closing"),this.chatWindow?.classList.add("open"),this.stopTitleBlink(),this.updateUnreadBadge();let e=this.chatWindow?.querySelector(".basjoo-input");setTimeout(()=>{e?.focus()},300)}close(){this.isOpen=!1,this.chatWindow?.classList.remove("open"),this.chatWindow?.classList.add("closing")}getRequestLocale(){return this.config.language&&this.config.language!=="auto"?this.config.language:navigator.language||"en-US"}getText(e){let t={sendFailed:{"en-US":"Send failed, please try again later","zh-CN":"\u53D1\u9001\u5931\u8D25\uFF0C\u8BF7\u7A0D\u540E\u91CD\u8BD5"},networkError:{"en-US":"Network connection failed, please check your connection","zh-CN":"\u7F51\u7EDC\u8FDE\u63A5\u5931\u8D25\uFF0C\u8BF7\u68C0\u67E5\u7F51\u7EDC"},quotaExceeded:{"en-US":"Daily message limit reached","zh-CN":"\u4ECA\u65E5\u6D88\u606F\u5DF2\u8FBE\u4E0A\u9650"},takenOverNotice:{"en-US":"Your conversation has been transferred to a human agent. Please wait for their reply.","zh-CN":"\u5DF2\u8F6C\u63A5\u4EBA\u5DE5\u5BA2\u670D\uFF0C\u8BF7\u7B49\u5F85\u56DE\u590D\u3002"},handoffPendingNotice:{"en-US":"Your request for a human agent has been received. Please wait for assistance.","zh-CN":"\u5DF2\u6536\u5230\u4F60\u7684\u4EBA\u5DE5\u5BA2\u670D\u8BF7\u6C42\uFF0C\u8BF7\u7A0D\u5019\uFF0C\u6211\u4EEC\u4F1A\u5C3D\u5FEB\u5904\u7406\u3002"},handoffButton:{"en-US":"Human","zh-CN":"\u8F6C\u4EBA\u5DE5"},handoffRequestedButton:{"en-US":"Requested","zh-CN":"\u5DF2\u8BF7\u6C42"},handoffFailed:{"en-US":"Failed to request a human agent. Please try again.","zh-CN":"\u8BF7\u6C42\u4EBA\u5DE5\u5BA2\u670D\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002"},inputPlaceholder:{"en-US":"Type your question...","zh-CN":"\u8F93\u5165\u60A8\u7684\u95EE\u9898..."},messageTooLong:{"en-US":"Message too long (max 2000 characters)","zh-CN":"\u6D88\u606F\u8FC7\u957F\uFF08\u6700\u591A2000\u5B57\u7B26\uFF09"},greetingBubble:{"en-US":"Hi! How can I help you?","zh-CN":"\u4F60\u597D\uFF01\u6709\u4EC0\u4E48\u53EF\u4EE5\u5E2E\u60A8\uFF1F"},newMessage:{"en-US":"New message","zh-CN":"\u65B0\u6D88\u606F"},thinking:{"en-US":"Thinking...","zh-CN":"\u601D\u8003\u4E2D..."},references:{"en-US":"References","zh-CN":"\u53C2\u8003\u6765\u6E90"}};return this.getRequestLocale().toLowerCase().startsWith("zh")?t[e]["zh-CN"]||t[e]["en-US"]||e:t[e]["en-US"]||t[e]["zh-CN"]||e}escapeHtml(e){return e.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;")}sanitizeUrlAttribute(e){let t=this.getSafeHttpUrl(e);return t?this.escapeHtml(t):""}getSafeHttpUrl(e){try{let t=new URL(e);if(t.protocol==="http:"||t.protocol==="https:")return e}catch{}return""}renderMarkdown(e){if(!e)return"";let t=e.replace(/\r\n/g,`
`).split(/\n{2,}/).map(s=>s.trim()).filter(Boolean),i=s=>{let o=this.escapeHtml(s);return o=o.replace(/`([^`]+)`/g,"<code>$1</code>"),o=o.replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>"),o=o.replace(/__([^_]+)__/g,"<strong>$1</strong>"),o=o.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g,"$1<em>$2</em>"),o=o.replace(/(^|[^_])_([^_]+)_(?!_)/g,"$1<em>$2</em>"),o=o.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,(a,c,l)=>{let g=c,u=this.sanitizeUrlAttribute(l);return u?`<a href="${u}" target="_blank" rel="noopener noreferrer">${g}</a>`:g}),o};return t.map(s=>{if(/^```/.test(s)&&/```$/.test(s)){let o=s.replace(/^```\w*\n?/,"").replace(/```$/,"");return`<pre><code>${this.escapeHtml(o)}</code></pre>`}if(/^(?:[-*]\s.+\n?)+$/.test(s))return`<ul>${s.split(`
`).map(a=>a.replace(/^[-*]\s+/,"").trim()).filter(Boolean).map(a=>`<li>${i(a)}</li>`).join("")}</ul>`;if(/^(?:\d+\.\s.+\n?)+$/.test(s))return`<ol>${s.split(`
`).map(a=>a.replace(/^\d+\.\s+/,"").trim()).filter(Boolean).map(a=>`<li>${i(a)}</li>`).join("")}</ol>`;if(/^>\s?/.test(s)){let o=s.split(`
`).map(a=>a.replace(/^>\s?/,"")).join("<br>");return`<blockquote>${i(o)}</blockquote>`}if(/^#{1,6}\s/.test(s)){let o=s.replace(/^#{1,6}\s+/,"");return`<p><strong>${i(o)}</strong></p>`}return`<p>${i(s).replace(/\n/g,"<br>")}</p>`}).join("")}updateMessageContent(e,t,i=!1){e.innerHTML=this.renderMarkdown(t)+(i?'<span class="basjoo-stream-cursor"></span>':"")}createReferenceList(e){if(e.length===0)return null;let t=document.createElement("div");t.className="basjoo-references";let i=document.createElement("div");i.className="basjoo-references-title",i.textContent=this.getText("references"),t.appendChild(i);for(let[n,s]of e.entries()){let o=s.type==="url"?document.createElement("a"):document.createElement("div");if(o.className="basjoo-reference-card",o instanceof HTMLAnchorElement&&s.url){let c=this.getSafeHttpUrl(s.url);if(!c)continue;o.href=c,o.target="_blank",o.rel="noopener noreferrer"}let a=document.createElement("div");if(a.className="basjoo-reference-name",a.textContent=`${n+1}. ${s.type==="file"?"\u{1F4C4}":"\u2197"} ${s.title}`,o.appendChild(a),s.snippet){let c=document.createElement("div");c.className="basjoo-reference-snippet",c.textContent=s.snippet,o.appendChild(c)}t.appendChild(o)}return t.childElementCount>1?t:null}createMessageElement(e){let t=document.createElement("div");t.className=`basjoo-message basjoo-message-${e.role}`;let i=document.createElement("div");if(i.className="basjoo-message-content",e.role==="assistant"){let s=w(e.content,e.sources);this.updateMessageContent(i,s.content);let o=this.createReferenceList(s.references);o&&i.appendChild(o)}else this.updateMessageContent(i,e.content);t.appendChild(i);let n=document.createElement("div");return n.className="basjoo-message-time",n.textContent=e.timestamp.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}),t.appendChild(n),t}formatThinkingText(){return`${this.getText("thinking")} ${this.thinkingElapsed}s`}showThinkingIndicator(e=0){this.hideLoading(),this.currentStreamContent.trim()||(this.streamingMessage?.remove(),this.streamingMessage=null,this.streamingMessageContent=null),this.thinkingElapsed=e;let t=this.chatWindow?.querySelector(".basjoo-messages");if(t){if(!this.thinkingIndicator){let i=document.createElement("div");i.className="basjoo-thinking",i.innerHTML=`
        <span class="basjoo-thinking-spinner"></span>
        <span>${this.getText("thinking")}</span>
      `,t.appendChild(i),this.thinkingIndicator=i,this.thinkingIndicatorText=i.querySelector("span:last-child")}this.thinkingIndicatorText&&(this.thinkingIndicatorText.textContent=this.formatThinkingText()),t.scrollTop=t.scrollHeight,this.thinkingTimerId===null&&(this.thinkingTimerId=window.setInterval(()=>{this.thinkingElapsed+=1,this.thinkingIndicatorText&&(this.thinkingIndicatorText.textContent=this.formatThinkingText())},1e3))}}hideThinkingIndicator(){this.thinkingTimerId!==null&&(window.clearInterval(this.thinkingTimerId),this.thinkingTimerId=null),this.thinkingIndicator?.remove(),this.thinkingIndicator=null,this.thinkingIndicatorText=null,this.thinkingElapsed=0}removeStreamingMessage(){this.streamingMessage?.remove(),this.streamingMessage=null,this.streamingMessageContent=null,this.currentStreamContent="",this.currentStreamSources=[]}createStreamingMessage(e=!1){let t=this.chatWindow?.querySelector(".basjoo-messages"),i=document.createElement("div");i.className="basjoo-message basjoo-message-assistant";let n=document.createElement("div");return n.className="basjoo-message-content",this.updateMessageContent(n,this.currentStreamContent,e),i.appendChild(n),t?(t.appendChild(i),t.scrollTop=t.scrollHeight,this.streamingMessage=i,this.streamingMessageContent=n,this.currentStreamContent="",i):(this.streamingMessage=i,this.streamingMessageContent=n,this.currentStreamContent="",i)}appendToStreamingMessage(e){(!this.streamingMessage||!this.streamingMessageContent)&&(this.hideThinkingIndicator(),this.createStreamingMessage()),this.currentStreamContent+=e,this.streamingMessageContent&&this.updateMessageContent(this.streamingMessageContent,this.currentStreamContent,!0);let t=this.chatWindow?.querySelector(".basjoo-messages");t&&(t.scrollTop=t.scrollHeight)}finalizeStreamingMessage(e=[]){if(!this.streamingMessage||!this.streamingMessageContent)return;if(!this.currentStreamContent.trim()){this.removeStreamingMessage();return}this.streamingMessage.querySelector(".basjoo-stream-cursor")?.remove(),this.currentStreamSources=e;let i=w(this.currentStreamContent,e);this.updateMessageContent(this.streamingMessageContent,i.content);let n=this.createReferenceList(i.references);n&&this.streamingMessageContent.appendChild(n),this.messages.push({role:"assistant",content:this.currentStreamContent,sources:e,timestamp:new Date});let s=this.chatWindow?.querySelector(".basjoo-messages");s.scrollTop=s.scrollHeight,this.streamingMessage=null,this.streamingMessageContent=null,this.currentStreamContent="",this.currentStreamSources=[]}addMessage(e){this.messages.push(e);let t=this.chatWindow?.querySelector(".basjoo-messages");if(!e.content){console.error("Message content is null or undefined:",e);return}if(!t)return;let i=this.createMessageElement(e);t.appendChild(i),t.scrollTop=t.scrollHeight,e.role==="assistant"&&!this.isOpen&&(this.hasUnread=!0,this.updateUnreadBadge())}showLoading(){let e=this.chatWindow?.querySelector(".basjoo-messages");if(!e)return;let t=document.createElement("div");t.className="basjoo-loading",t.id="basjoo-loading",t.innerHTML=`
      <div class="basjoo-loading-dot"></div>
      <div class="basjoo-loading-dot"></div>
      <div class="basjoo-loading-dot"></div>
    `,e.appendChild(t),e.scrollTop=e.scrollHeight}hideLoading(){this.chatWindow?.querySelector("#basjoo-loading")?.remove()}showError(e){let t=this.chatWindow?.querySelector(".basjoo-messages");if(!t)return;let i=document.createElement("div");i.className="basjoo-error",i.textContent=e,t.appendChild(i),t.scrollTop=t.scrollHeight,setTimeout(()=>i.remove(),5e3)}startPolling(){this.pollIntervalId||(this.pollIntervalId=window.setInterval(()=>this.pollMessages(),3e3))}stopPolling(){this.pollIntervalId&&(clearInterval(this.pollIntervalId),this.pollIntervalId=null)}updateHandoffButton(){let e=this.chatWindow?.querySelector(".basjoo-handoff");e&&(e.textContent=this.getText(this.handoffRequested?"handoffRequestedButton":"handoffButton"),e.disabled=!this.sessionId||this.handoffRequested||this.isSending||this.isRequestingHandoff)}async requestHumanHandoff(){if(!(!this.sessionId||this.handoffRequested||this.isRequestingHandoff||this.isSending)){this.isRequestingHandoff=!0,this.updateHandoffButton();try{let e=await fetch(`${this.config.apiBase}/api/v1/chat/handoff`,{method:"POST",headers:{"Content-Type":"application/json",...this.getVisitorAuthHeaders()},body:JSON.stringify({agent_id:this.config.agentId,session_id:this.sessionId,visitor_id:this.visitorId,locale:this.getRequestLocale()})});if(!e.ok)throw new Error(`HTTP ${e.status}: ${e.statusText}`);let t=await e.json();this.handoffRequested=!0,typeof t.message_id=="number"&&t.message_id>this.lastMessageId&&(this.lastMessageId=t.message_id),t.created&&t.message&&this.addMessage({role:"assistant",content:t.message,timestamp:new Date}),this.startPolling()}catch(e){console.error("[Basjoo Widget] Failed to request human handoff:",e),this.showError(this.getText("handoffFailed"))}finally{this.isRequestingHandoff=!1,this.updateHandoffButton()}}}async pollMessages(){if(this.sessionId)try{let e=await fetch(`${this.config.apiBase}/api/v1/chat/messages?session_id=${encodeURIComponent(this.sessionId)}&after_id=${this.lastMessageId}&role=assistant`,{headers:this.getVisitorAuthHeaders()});if(!e.ok)return;let t=await e.json();for(let i of t)i.content&&(this.addMessage({role:i.role==="user"?"user":"assistant",content:i.content,sources:i.sources,timestamp:new Date}),this.isOpen||this.startTitleBlink()),i.id>this.lastMessageId&&(this.lastMessageId=i.id)}catch{}}cleanupAfterStreamError(){this.hideLoading(),this.hideThinkingIndicator(),this.removeStreamingMessage()}async consumeStream(e){if(!e.body)throw new Error("Streaming response body is unavailable");let t=e.body.getReader(),i=new TextDecoder,n="",s=!1,o=l=>{if(!l.trim())return;let g="message",u=[];for(let d of l.split(`
`))d.startsWith("event:")?g=d.slice(6).trim():d.startsWith("data:")&&u.push(d.slice(5).trimStart());if(!u.length)return;let h=JSON.parse(u.join(`
`));switch(g){case"sources":this.currentStreamSources=Array.isArray(h.sources)?h.sources:[];break;case"thinking":this.showThinkingIndicator(typeof h.elapsed=="number"?h.elapsed:0);break;case"thinking_done":this.hideThinkingIndicator();break;case"content":{let d=h.content||"";this.appendToStreamingMessage(d);break}case"done":{let d=h;d.visitor_token&&(this.visitorToken=d.visitor_token,this.storage.setItem(this.VISITOR_TOKEN_STORAGE_KEY,d.visitor_token)),d.session_id&&(this.sessionId=d.session_id,this.storage.setItem(this.STORAGE_KEY,d.session_id),this.startPolling(),this.updateHandoffButton()),typeof d.message_id=="number"&&d.message_id>this.lastMessageId&&(this.lastMessageId=d.message_id),d.taken_over?(this.handoffRequested=!0,this.updateHandoffButton(),this.removeStreamingMessage(),this.addMessage({role:"assistant",content:this.getText("takenOverNotice"),timestamp:new Date})):d.handoff_requested?(this.removeStreamingMessage(),this.handoffRequested||this.addMessage({role:"assistant",content:this.getText("handoffPendingNotice"),timestamp:new Date}),this.handoffRequested=!0,this.updateHandoffButton()):(this.finalizeStreamingMessage(this.currentStreamSources),this.isOpen||this.startTitleBlink()),s=!0;break}case"error":{let d=h,f=new Error(d.error||"Stream failed");throw d.code&&(f.name=d.code),f}default:break}},a=()=>{let l=n.indexOf(`\r
\r
`),g=n.indexOf(`

`);return l===-1&&g===-1?null:l===-1?{index:g,length:2}:g===-1?{index:l,length:4}:l<g?{index:l,length:4}:{index:g,length:2}},c=9e4;for(;!s;){if(this.streamAbortController?.signal.aborted){t.cancel();return}let l=null;try{let{done:g,value:u}=await Promise.race([t.read(),new Promise((d,f)=>{l=window.setTimeout(()=>f(new Error("Stream read timeout")),c)})]);n+=i.decode(u||new Uint8Array,{stream:!g});let h=a();for(;h;){let d=n.slice(0,h.index);if(n=n.slice(h.index+h.length),o(d.replace(/\r\n/g,`
`)),s)break;h=a()}if(g)break}finally{l!==null&&window.clearTimeout(l)}}if(!s&&(n.trim()&&o(n),!s))throw new Error("Stream ended unexpectedly")}abortStream(){this.streamAbortController?.abort(),this.streamAbortController=null}async sendMessageWithRetry(e){let t=null;for(let i=0;i<=1;i++){this.abortStream(),this.streamAbortController=new AbortController;try{let n=Intl.DateTimeFormat().resolvedOptions().timeZone,s=await fetch(`${this.config.apiBase}/api/v1/chat/stream`,{method:"POST",headers:{"Content-Type":"application/json",Accept:"text/event-stream",...this.getVisitorAuthHeaders()},signal:this.streamAbortController.signal,body:JSON.stringify({agent_id:this.config.agentId,message:e,locale:this.getRequestLocale(),session_id:this.sessionId||void 0,visitor_id:this.visitorId,timezone:n})});if(!s.ok){let o=`HTTP ${s.status}: ${s.statusText}`;try{let a=await s.json();o=a.message||a.detail||o}catch{}throw new Error(o)}this.hideLoading(),await this.consumeStream(s);return}catch(n){t=n;let s=String(n?.message||"");if(!(!(this.currentStreamContent.trim().length>0)&&(n instanceof TypeError||s.includes("fetch")||s.includes("Failed to fetch")||s.includes("Stream ended unexpectedly")))||i>=1)throw this.cleanupAfterStreamError(),n;this.cleanupAfterStreamError(),console.warn(`[Basjoo Widget] Stream attempt ${i+1} failed, retrying...`),await new Promise(c=>window.setTimeout(c,1e3)),this.showLoading()}}throw t}async sendMessage(e){if(!this.isSending){this.isSending=!0,this.updateHandoffButton(),this.addMessage({role:"user",content:e,timestamp:new Date}),this.hideLoading(),this.hideThinkingIndicator(),this.removeStreamingMessage(),this.createStreamingMessage(!0);try{await this.sendMessageWithRetry(e)}catch(t){console.error("[Basjoo Widget] Error sending message:",t);let i=this.getText("sendFailed"),n="",s=String(t?.message||"");t instanceof TypeError||s.includes("fetch")?(i=this.getText("networkError"),n=`Request may be blocked by CORS, network connectivity, or an incorrect apiBase. Current apiBase: ${this.config.apiBase||"(not set)"}`):s.includes("429")||s.toLowerCase().includes("quota")?i=this.getText("quotaExceeded"):t?.name==="ORIGIN_NOT_ALLOWED"||s.toLowerCase().includes("widget origin not allowed")?(i=this.getText("sendFailed"),n="Widget request was blocked because the current page origin is not on the allowed domain list."):s.includes("401")&&(n="Authentication failed. Please check the agent configuration and public API access."),this.config.apiBase||(n="apiBase could not be determined. When embedding the widget from a local file, set apiBase explicitly or load the SDK from the target server."),n&&console.error("[Basjoo Widget]",n),this.showError(i)}finally{this.isSending=!1,this.updateHandoffButton()}}}destroy(){this.stopPolling(),this.stopTitleBlink(),this.hideThinkingIndicator(),this.removeStreamingMessage(),this.abortStream(),this.button&&this._buttonClickListener&&this.button.removeEventListener("click",this._buttonClickListener);let e=this.chatWindow?.querySelector(".basjoo-close");e&&this._closeBtnClickListener&&e.removeEventListener("click",this._closeBtnClickListener);let t=this.chatWindow?.querySelector(".basjoo-send");t&&this._sendBtnClickListener&&t.removeEventListener("click",this._sendBtnClickListener);let i=this.chatWindow?.querySelector(".basjoo-input");i&&this._inputKeypressListener&&i.removeEventListener("keypress",this._inputKeypressListener);let n=this.chatWindow?.querySelector(".basjoo-handoff");n&&this._handoffClickListener&&n.removeEventListener("click",this._handoffClickListener),this.container?.remove(),document.getElementById("basjoo-widget-styles")?.remove()}};window.BasjooWidget=b;function m(r,e){for(let t of e){let i=r.get(t);if(i&&i.trim())return i.trim()}return null}function T(){if(document.currentScript instanceof HTMLScriptElement)return document.currentScript;let r=Array.from(document.querySelectorAll("script[src]"));for(let e=r.length-1;e>=0;e-=1){let t=r[e],i=t.getAttribute("src")||"";if(i.includes("sdk.js"))try{let n=new URL(i,window.location.href);if(m(n.searchParams,p.agentId))return t}catch{continue}}return null}function C(r){let e=r.getAttribute("src")||r.src;if(!e)return null;let t;try{t=new URL(e,window.location.href)}catch{return null}let i=m(t.searchParams,p.agentId);if(!i)return null;let n={agentId:i},s=m(t.searchParams,p.apiBase);s&&(n.apiBase=s);let o=m(t.searchParams,p.themeColor);o&&(n.themeColor=o);let a=m(t.searchParams,p.welcomeMessage);a&&(n.welcomeMessage=a);let c=m(t.searchParams,p.language);c&&(n.language=c);let l=m(t.searchParams,p.position);(l==="left"||l==="right")&&(n.position=l);let g=m(t.searchParams,p.theme);return(g==="light"||g==="dark"||g==="auto")&&(n.theme=g),n}(function(){let e=window,t=T();if(!t)return;let i=C(t);if(!i||e.__basjooWidgetAutoInitScheduled)return;e.__basjooWidgetAutoInitScheduled=!0;let n=()=>{new b(i).init()};if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",n,{once:!0});return}n()})();})();
//# sourceMappingURL=basjoo-widget.min.js.map
