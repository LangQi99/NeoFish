"use strict";
/// <reference types="../../../../../.npm/_npx/2db181330ea4b15b/node_modules/@vue/language-core/types/template-helpers.d.ts" />
/// <reference types="../../../../../.npm/_npx/2db181330ea4b15b/node_modules/@vue/language-core/types/props-fallback.d.ts" />
var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
var __spreadArray = (this && this.__spreadArray) || function (to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
        if (ar || !(i in from)) {
            if (!ar) ar = Array.prototype.slice.call(from, 0, i);
            ar[i] = from[i];
        }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
};
Object.defineProperty(exports, "__esModule", { value: true });
var vue_1 = require("vue");
var Sidebar_vue_1 = require("./components/Sidebar.vue");
var MainInput_vue_1 = require("./components/MainInput.vue");
var useChatHistory_1 = require("./composables/useChatHistory");
var _a = (0, useChatHistory_1.useChatHistory)(), sessions = _a.sessions, activeChatId = _a.activeChatId, loadSessions = _a.loadSessions, createNewChat = _a.createNewChat, refreshSession = _a.refreshSession;
// ─── WebSocket ─────────────────────────────────────────────────────────────
var ws = (0, vue_1.ref)(null);
var isConnected = (0, vue_1.ref)(false);
// Tracks whether a browser-takeover is currently active
var isInTakeover = (0, vue_1.ref)(false);
function connectWs(sessionId) {
    if (ws.value) {
        ws.value.onclose = null; // prevent auto-reconnect on intentional close
        ws.value.close();
    }
    var socket = new WebSocket("ws://localhost:8000/ws/agent?session_id=".concat(sessionId));
    ws.value = socket;
    socket.onopen = function () {
        isConnected.value = true;
    };
    socket.onmessage = function (event) {
        var data = JSON.parse(event.data);
        // If server echoes back a session_id (on connection), sync it
        if (data.session_id && data.session_id !== activeChatId.value) {
            activeChatId.value = data.session_id;
        }
        // Handle takeover lifecycle messages
        if (data.type === 'takeover_started') {
            isInTakeover.value = true;
        }
        else if (data.type === 'takeover_ended') {
            isInTakeover.value = false;
        }
        pushMessage(data);
    };
    socket.onclose = function () {
        isConnected.value = false;
        isInTakeover.value = false;
        // Re-connect after 3s
        setTimeout(function () {
            if (activeChatId.value)
                connectWs(activeChatId.value);
        }, 3000);
    };
}
// ─── Messages for current session ─────────────────────────────────────────
var messages = (0, vue_1.ref)([]);
var hasStarted = (0, vue_1.ref)(false);
var scrollContainer = (0, vue_1.ref)(null);
function scrollToBottom() {
    (0, vue_1.nextTick)(function () {
        if (scrollContainer.value) {
            scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight;
        }
    });
}
(0, vue_1.watch)(messages, scrollToBottom, { deep: true });
function pushMessage(data) {
    messages.value.push(data);
    // Update sidebar preview after agent/user messages
    if (activeChatId.value && (data.type === 'info' || data.type === 'user')) {
        var preview = (data.message || '').slice(0, 80);
        refreshSession(activeChatId.value, { preview: preview });
    }
}
// ─── Session switching ─────────────────────────────────────────────────────
var loadMessages = (0, useChatHistory_1.useChatHistory)().loadMessages;
function switchToSession(id) {
    return __awaiter(this, void 0, void 0, function () {
        var hist;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    activeChatId.value = id;
                    messages.value = [];
                    hasStarted.value = false;
                    isInTakeover.value = false;
                    return [4 /*yield*/, loadMessages(id)];
                case 1:
                    hist = _a.sent();
                    if (hist.length > 0) {
                        hasStarted.value = true;
                        messages.value = hist.map(function (m) {
                            var _a;
                            // Check if this is an image message from agent
                            if (m.role === 'assistant' && m.image_data) {
                                if (m.content.startsWith('[Action Required]')) {
                                    return {
                                        type: 'action_required',
                                        reason: m.content.replace('[Action Required] ', ''),
                                        image: m.image_data
                                    };
                                }
                                else if (m.content.startsWith('[Image]')) {
                                    return {
                                        type: 'image',
                                        description: m.content.replace('[Image] ', ''),
                                        image: m.image_data
                                    };
                                }
                                else if (m.content.startsWith('[Takeover Ended]')) {
                                    return {
                                        type: 'takeover_ended',
                                        message: m.content.replace('[Takeover Ended] ', ''),
                                        image: m.image_data
                                    };
                                }
                            }
                            return {
                                type: m.role === 'user' ? 'user' : 'info',
                                message: m.content,
                                images: (_a = m.images) !== null && _a !== void 0 ? _a : [],
                            };
                        });
                    }
                    connectWs(id);
                    return [2 /*return*/];
            }
        });
    });
}
// ─── New chat ──────────────────────────────────────────────────────────────
function handleNewChat() {
    return __awaiter(this, void 0, void 0, function () {
        return __generator(this, function (_a) {
            // createNewChat already called in Sidebar → we just switch to the new active session
            messages.value = [];
            hasStarted.value = false;
            isInTakeover.value = false;
            if (activeChatId.value) {
                connectWs(activeChatId.value);
            }
            return [2 /*return*/];
        });
    });
}
// ─── User submit ───────────────────────────────────────────────────────────
function handleUserSubmit(payload) {
    var text = payload.text, images = payload.images;
    hasStarted.value = true;
    pushMessage({ type: 'user', message: text, images: images });
    if (ws.value && isConnected.value) {
        ws.value.send(JSON.stringify({ type: 'user_input', message: text, images: images }));
    }
    // Update title of session in sidebar to first message
    var sid = activeChatId.value;
    var session = sessions.value.find(function (s) { return s.id === sid; });
    if (sid && session && (!session.title || session.title === 'New Chat')) {
        refreshSession(sid, { title: (text || '📷 Image').slice(0, 40) });
    }
}
function resumeAgent() {
    if (ws.value && isConnected.value) {
        ws.value.send(JSON.stringify({ type: 'resume' }));
        pushMessage({ type: 'info', message: '已发送继续执行指令。' });
    }
}
/** Open the headed browser for direct user interaction. */
function requestTakeover() {
    if (ws.value && isConnected.value) {
        ws.value.send(JSON.stringify({ type: 'takeover' }));
    }
}
/** Signal that the user is finished without closing the browser window. */
function signalTakeoverDone() {
    if (ws.value && isConnected.value) {
        ws.value.send(JSON.stringify({ type: 'takeover_done' }));
    }
}
// ─── Lifecycle ─────────────────────────────────────────────────────────────
(0, vue_1.onMounted)(function () { return __awaiter(void 0, void 0, void 0, function () {
    var session;
    return __generator(this, function (_a) {
        switch (_a.label) {
            case 0: return [4 /*yield*/, loadSessions()];
            case 1:
                _a.sent();
                if (!(sessions.value.length > 0 && sessions.value[0])) return [3 /*break*/, 3];
                return [4 /*yield*/, switchToSession(sessions.value[0].id)];
            case 2:
                _a.sent();
                return [3 /*break*/, 5];
            case 3: return [4 /*yield*/, createNewChat()];
            case 4:
                session = _a.sent();
                connectWs(session.id);
                _a.label = 5;
            case 5: return [2 /*return*/];
        }
    });
}); });
(0, vue_1.onUnmounted)(function () {
    if (ws.value) {
        ws.value.onclose = null;
        ws.value.close();
    }
});
var __VLS_ctx = __assign(__assign({}, {}), {});
var __VLS_components;
var __VLS_intrinsics;
var __VLS_directives;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "h-screen w-full flex bg-[#FDFBF7] font-sans selection:bg-neutral-200" }));
/** @type {__VLS_StyleScopedClasses['h-screen']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-[#FDFBF7]']} */ ;
/** @type {__VLS_StyleScopedClasses['font-sans']} */ ;
/** @type {__VLS_StyleScopedClasses['selection:bg-neutral-200']} */ ;
var __VLS_0 = Sidebar_vue_1.default;
// @ts-ignore
var __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0(__assign({ 'onNewChat': {} }, { 'onSelectChat': {} })));
var __VLS_2 = __VLS_1.apply(void 0, __spreadArray([__assign({ 'onNewChat': {} }, { 'onSelectChat': {} })], __VLS_functionalComponentArgsRest(__VLS_1), false));
var __VLS_5;
var __VLS_6 = ({ newChat: {} },
    { onNewChat: (__VLS_ctx.handleNewChat) });
var __VLS_7 = ({ selectChat: {} },
    { onSelectChat: (__VLS_ctx.switchToSession) });
var __VLS_3;
var __VLS_4;
__VLS_asFunctionalElement1(__VLS_intrinsics.main, __VLS_intrinsics.main)(__assign({ class: "flex-1 flex flex-col relative h-full" }, { style: {} }));
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['relative']} */ ;
/** @type {__VLS_StyleScopedClasses['h-full']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.header, __VLS_intrinsics.header)(__assign({ class: "absolute top-0 left-0 w-full p-6 flex justify-end gap-3 z-10 pointer-events-none" }));
/** @type {__VLS_StyleScopedClasses['absolute']} */ ;
/** @type {__VLS_StyleScopedClasses['top-0']} */ ;
/** @type {__VLS_StyleScopedClasses['left-0']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['p-6']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-end']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
/** @type {__VLS_StyleScopedClasses['z-10']} */ ;
/** @type {__VLS_StyleScopedClasses['pointer-events-none']} */ ;
var __VLS_8;
/** @ts-ignore @type {typeof __VLS_components.Transition | typeof __VLS_components.Transition} */
Transition;
// @ts-ignore
var __VLS_9 = __VLS_asFunctionalComponent1(__VLS_8, new __VLS_8({
    enterActiveClass: "transition-all duration-300 ease-out",
    leaveActiveClass: "transition-all duration-200 ease-in",
    enterFromClass: "opacity-0 scale-95",
    leaveToClass: "opacity-0 scale-95",
}));
var __VLS_10 = __VLS_9.apply(void 0, __spreadArray([{
        enterActiveClass: "transition-all duration-300 ease-out",
        leaveActiveClass: "transition-all duration-200 ease-in",
        enterFromClass: "opacity-0 scale-95",
        leaveToClass: "opacity-0 scale-95",
    }], __VLS_functionalComponentArgsRest(__VLS_9), false));
var __VLS_13 = __VLS_11.slots.default;
if (__VLS_ctx.isInTakeover) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex items-center gap-2 bg-amber-50 border border-amber-300 px-3 py-1.5 rounded-full shadow-sm pointer-events-auto" }));
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-amber-50']} */ ;
    /** @type {__VLS_StyleScopedClasses['border']} */ ;
    /** @type {__VLS_StyleScopedClasses['border-amber-300']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-3']} */ ;
    /** @type {__VLS_StyleScopedClasses['py-1.5']} */ ;
    /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
    /** @type {__VLS_StyleScopedClasses['pointer-events-auto']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-2 h-2 rounded-full bg-amber-500 animate-pulse" }));
    /** @type {__VLS_StyleScopedClasses['w-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['h-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-amber-500']} */ ;
    /** @type {__VLS_StyleScopedClasses['animate-pulse']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "text-xs font-medium text-amber-700" }));
    /** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-amber-700']} */ ;
    (__VLS_ctx.$t('common.takeover_banner'));
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ onClick: (__VLS_ctx.signalTakeoverDone) }, { class: "ml-1 text-xs font-semibold text-amber-800 hover:text-amber-900 bg-amber-100 hover:bg-amber-200 px-2 py-0.5 rounded-full transition-colors" }));
    /** @type {__VLS_StyleScopedClasses['ml-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-amber-800']} */ ;
    /** @type {__VLS_StyleScopedClasses['hover:text-amber-900']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-amber-100']} */ ;
    /** @type {__VLS_StyleScopedClasses['hover:bg-amber-200']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['py-0.5']} */ ;
    /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
    (__VLS_ctx.$t('common.takeover_done_button'));
}
// @ts-ignore
[handleNewChat, switchToSession, isInTakeover, $t, $t, signalTakeoverDone,];
var __VLS_11;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex items-center gap-2 bg-white/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-neutral-200/50 shadow-sm pointer-events-auto" }));
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-white/80']} */ ;
/** @type {__VLS_StyleScopedClasses['backdrop-blur-md']} */ ;
/** @type {__VLS_StyleScopedClasses['px-3']} */ ;
/** @type {__VLS_StyleScopedClasses['py-1.5']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-neutral-200/50']} */ ;
/** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['pointer-events-auto']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-2 h-2 rounded-full" }, { class: (__VLS_ctx.isConnected ? 'bg-green-500' : 'bg-red-500') }));
/** @type {__VLS_StyleScopedClasses['w-2']} */ ;
/** @type {__VLS_StyleScopedClasses['h-2']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "text-xs font-medium text-neutral-600" }));
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
/** @type {__VLS_StyleScopedClasses['text-neutral-600']} */ ;
(__VLS_ctx.isConnected ? __VLS_ctx.$t('common.agent_ready') : __VLS_ctx.$t('common.connecting'));
if (__VLS_ctx.hasStarted && __VLS_ctx.isConnected && !__VLS_ctx.isInTakeover) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign(__assign({ onClick: (__VLS_ctx.requestTakeover) }, { class: "ml-1 text-xs font-semibold text-neutral-500 hover:text-neutral-800 bg-neutral-100 hover:bg-neutral-200 px-2 py-0.5 rounded-full transition-colors" }), { title: (__VLS_ctx.$t('common.proactive_takeover')) }));
    /** @type {__VLS_StyleScopedClasses['ml-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-neutral-500']} */ ;
    /** @type {__VLS_StyleScopedClasses['hover:text-neutral-800']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-neutral-100']} */ ;
    /** @type {__VLS_StyleScopedClasses['hover:bg-neutral-200']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['py-0.5']} */ ;
    /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
    (__VLS_ctx.$t('common.proactive_takeover'));
}
if (!__VLS_ctx.hasStarted) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex-1 overflow-hidden transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] opacity-100 translate-y-0" }));
    /** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['overflow-hidden']} */ ;
    /** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
    /** @type {__VLS_StyleScopedClasses['duration-700']} */ ;
    /** @type {__VLS_StyleScopedClasses['ease-[cubic-bezier(0.16,1,0.3,1)]']} */ ;
    /** @type {__VLS_StyleScopedClasses['opacity-100']} */ ;
    /** @type {__VLS_StyleScopedClasses['translate-y-0']} */ ;
    var __VLS_14 = MainInput_vue_1.default;
    // @ts-ignore
    var __VLS_15 = __VLS_asFunctionalComponent1(__VLS_14, new __VLS_14(__assign({ 'onSubmit': {} })));
    var __VLS_16 = __VLS_15.apply(void 0, __spreadArray([__assign({ 'onSubmit': {} })], __VLS_functionalComponentArgsRest(__VLS_15), false));
    var __VLS_19 = void 0;
    var __VLS_20 = ({ submit: {} },
        { onSubmit: (__VLS_ctx.handleUserSubmit) });
    var __VLS_17;
    var __VLS_18;
}
else {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex-1 flex flex-col max-w-4xl mx-auto w-full pt-20 pb-6 px-4 min-h-0" }));
    /** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
    /** @type {__VLS_StyleScopedClasses['max-w-4xl']} */ ;
    /** @type {__VLS_StyleScopedClasses['mx-auto']} */ ;
    /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['pt-20']} */ ;
    /** @type {__VLS_StyleScopedClasses['pb-6']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['min-h-0']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ ref: "scrollContainer" }, { class: "flex-1 overflow-y-auto space-y-6 pb-20 custom-scrollbar pr-4" }));
    /** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['overflow-y-auto']} */ ;
    /** @type {__VLS_StyleScopedClasses['space-y-6']} */ ;
    /** @type {__VLS_StyleScopedClasses['pb-20']} */ ;
    /** @type {__VLS_StyleScopedClasses['custom-scrollbar']} */ ;
    /** @type {__VLS_StyleScopedClasses['pr-4']} */ ;
    for (var _i = 0, _b = __VLS_vFor((__VLS_ctx.messages)); _i < _b.length; _i++) {
        var _c = _b[_i], msg = _c[0], idx = _c[1];
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign(__assign({ key: (idx) }, { class: "p-4 rounded-2xl max-w-[85%] animate-fade-in-up" }), { class: (msg.type === 'user' ? 'bg-neutral-100 text-neutral-800 ml-auto rounded-tr-sm' : 'bg-white border border-neutral-100 shadow-sm mr-auto rounded-tl-sm') }));
        /** @type {__VLS_StyleScopedClasses['p-4']} */ ;
        /** @type {__VLS_StyleScopedClasses['rounded-2xl']} */ ;
        /** @type {__VLS_StyleScopedClasses['max-w-[85%]']} */ ;
        /** @type {__VLS_StyleScopedClasses['animate-fade-in-up']} */ ;
        if (msg.type === 'user') {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col gap-2" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
            if (msg.images && msg.images.length > 0) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-wrap gap-2" }));
                /** @type {__VLS_StyleScopedClasses['flex']} */ ;
                /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
                /** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
                for (var _d = 0, _e = __VLS_vFor((msg.images)); _d < _e.length; _d++) {
                    var _f = _e[_d], src = _f[0], i = _f[1];
                    __VLS_asFunctionalElement1(__VLS_intrinsics.img)(__assign(__assign({ key: (i), src: (src) }, { class: "max-h-48 max-w-xs rounded-xl object-cover border border-neutral-200/60 shadow-sm" }), { alt: "attached image" }));
                    /** @type {__VLS_StyleScopedClasses['max-h-48']} */ ;
                    /** @type {__VLS_StyleScopedClasses['max-w-xs']} */ ;
                    /** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
                    /** @type {__VLS_StyleScopedClasses['object-cover']} */ ;
                    /** @type {__VLS_StyleScopedClasses['border']} */ ;
                    /** @type {__VLS_StyleScopedClasses['border-neutral-200/60']} */ ;
                    /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
                    // @ts-ignore
                    [isInTakeover, $t, $t, $t, $t, isConnected, isConnected, isConnected, hasStarted, hasStarted, requestTakeover, handleUserSubmit, messages,];
                }
            }
            if (msg.message) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "text-[15px] leading-relaxed" }));
                /** @type {__VLS_StyleScopedClasses['text-[15px]']} */ ;
                /** @type {__VLS_StyleScopedClasses['leading-relaxed']} */ ;
                (msg.message);
            }
        }
        else if (msg.type === 'info') {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex gap-3" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-6 h-6 rounded-full bg-neutral-900 flex-shrink-0 flex items-center justify-center" }));
            /** @type {__VLS_StyleScopedClasses['w-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['h-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
            /** @type {__VLS_StyleScopedClasses['bg-neutral-900']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "text-white text-[10px] font-bold" }));
            /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-[10px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "text-[15px] leading-relaxed text-neutral-700 font-serif" }));
            /** @type {__VLS_StyleScopedClasses['text-[15px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['leading-relaxed']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-neutral-700']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-serif']} */ ;
            (msg.type === 'info' && msg.message === 'Connected to NeoFish Agent WebSocket' ? __VLS_ctx.$t('common.connected_ws') : (msg.message_key ? __VLS_ctx.$t(msg.message_key, msg.params || {}) : msg.message));
        }
        else if (msg.type === 'takeover_started') {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col gap-3 w-full" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex gap-3" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-6 h-6 rounded-full bg-amber-500 flex-shrink-0 flex items-center justify-center shadow-sm" }));
            /** @type {__VLS_StyleScopedClasses['w-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['h-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
            /** @type {__VLS_StyleScopedClasses['bg-amber-500']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "text-white text-[11px] font-bold" }));
            /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-[11px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "text-[15px] leading-relaxed text-amber-800 font-medium pt-0.5" }));
            /** @type {__VLS_StyleScopedClasses['text-[15px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['leading-relaxed']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-amber-800']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
            /** @type {__VLS_StyleScopedClasses['pt-0.5']} */ ;
            (__VLS_ctx.$t('common.takeover_started'));
        }
        else if (msg.type === 'takeover_ended') {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col gap-3 w-full" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex gap-3" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-6 h-6 rounded-full bg-green-600 flex-shrink-0 flex items-center justify-center shadow-sm" }));
            /** @type {__VLS_StyleScopedClasses['w-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['h-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
            /** @type {__VLS_StyleScopedClasses['bg-green-600']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "text-white text-[11px] font-bold" }));
            /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-[11px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "text-[15px] leading-relaxed text-neutral-700 font-medium pt-0.5" }));
            /** @type {__VLS_StyleScopedClasses['text-[15px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['leading-relaxed']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-neutral-700']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
            /** @type {__VLS_StyleScopedClasses['pt-0.5']} */ ;
            (msg.message_key ? __VLS_ctx.$t(msg.message_key) : msg.message);
            if (msg.final_url) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "block text-xs text-neutral-400 mt-0.5 font-mono" }));
                /** @type {__VLS_StyleScopedClasses['block']} */ ;
                /** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
                /** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
                /** @type {__VLS_StyleScopedClasses['mt-0.5']} */ ;
                /** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
                (msg.final_url);
            }
            if (msg.image) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "mt-1 rounded-xl overflow-hidden border border-neutral-200/60 shadow-sm bg-neutral-50/50 p-2" }));
                /** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
                /** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
                /** @type {__VLS_StyleScopedClasses['overflow-hidden']} */ ;
                /** @type {__VLS_StyleScopedClasses['border']} */ ;
                /** @type {__VLS_StyleScopedClasses['border-neutral-200/60']} */ ;
                /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
                /** @type {__VLS_StyleScopedClasses['bg-neutral-50/50']} */ ;
                /** @type {__VLS_StyleScopedClasses['p-2']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.img)(__assign(__assign({ src: ('data:image/jpeg;base64,' + msg.image) }, { class: "w-full h-auto object-contain max-h-[400px] rounded-lg" }), { alt: "Final page state" }));
                /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
                /** @type {__VLS_StyleScopedClasses['h-auto']} */ ;
                /** @type {__VLS_StyleScopedClasses['object-contain']} */ ;
                /** @type {__VLS_StyleScopedClasses['max-h-[400px]']} */ ;
                /** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
            }
        }
        else if (msg.type === 'image') {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col gap-3 w-full" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex gap-3" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-6 h-6 rounded-full bg-neutral-900 flex-shrink-0 flex items-center justify-center" }));
            /** @type {__VLS_StyleScopedClasses['w-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['h-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
            /** @type {__VLS_StyleScopedClasses['bg-neutral-900']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "text-white text-[10px] font-bold" }));
            /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-[10px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "text-[15px] leading-relaxed text-neutral-700 font-serif" }));
            /** @type {__VLS_StyleScopedClasses['text-[15px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['leading-relaxed']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-neutral-700']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-serif']} */ ;
            (msg.description);
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "mt-1 rounded-xl overflow-hidden border border-neutral-200/60 shadow-sm bg-neutral-50/50 p-2" }));
            /** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
            /** @type {__VLS_StyleScopedClasses['overflow-hidden']} */ ;
            /** @type {__VLS_StyleScopedClasses['border']} */ ;
            /** @type {__VLS_StyleScopedClasses['border-neutral-200/60']} */ ;
            /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
            /** @type {__VLS_StyleScopedClasses['bg-neutral-50/50']} */ ;
            /** @type {__VLS_StyleScopedClasses['p-2']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.img)(__assign(__assign({ src: ('data:image/jpeg;base64,' + msg.image) }, { class: "w-full h-auto object-contain max-h-[400px] rounded-lg" }), { alt: "Screenshot" }));
            /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
            /** @type {__VLS_StyleScopedClasses['h-auto']} */ ;
            /** @type {__VLS_StyleScopedClasses['object-contain']} */ ;
            /** @type {__VLS_StyleScopedClasses['max-h-[400px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
        }
        else if (msg.type === 'action_required') {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col gap-4 w-full" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-4']} */ ;
            /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex gap-3" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-6 h-6 rounded-full bg-orange-500 flex-shrink-0 flex items-center justify-center shadow-sm" }));
            /** @type {__VLS_StyleScopedClasses['w-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['h-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
            /** @type {__VLS_StyleScopedClasses['bg-orange-500']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "text-white text-[12px] font-bold" }));
            /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-[12px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "text-[15px] leading-relaxed text-neutral-800 font-medium pt-0.5" }));
            /** @type {__VLS_StyleScopedClasses['text-[15px]']} */ ;
            /** @type {__VLS_StyleScopedClasses['leading-relaxed']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-neutral-800']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
            /** @type {__VLS_StyleScopedClasses['pt-0.5']} */ ;
            (__VLS_ctx.$t('common.action_required'));
            (msg.reason);
            if (msg.image) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "mt-2 rounded-xl overflow-hidden border border-neutral-200/60 shadow-sm bg-neutral-50/50 p-2" }));
                /** @type {__VLS_StyleScopedClasses['mt-2']} */ ;
                /** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
                /** @type {__VLS_StyleScopedClasses['overflow-hidden']} */ ;
                /** @type {__VLS_StyleScopedClasses['border']} */ ;
                /** @type {__VLS_StyleScopedClasses['border-neutral-200/60']} */ ;
                /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
                /** @type {__VLS_StyleScopedClasses['bg-neutral-50/50']} */ ;
                /** @type {__VLS_StyleScopedClasses['p-2']} */ ;
                __VLS_asFunctionalElement1(__VLS_intrinsics.img)(__assign(__assign({ src: ('data:image/jpeg;base64,' + msg.image) }, { class: "w-full h-auto object-contain max-h-[400px] rounded-lg" }), { alt: "Action Required" }));
                /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
                /** @type {__VLS_StyleScopedClasses['h-auto']} */ ;
                /** @type {__VLS_StyleScopedClasses['object-contain']} */ ;
                /** @type {__VLS_StyleScopedClasses['max-h-[400px]']} */ ;
                /** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
            }
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-wrap gap-3 mt-1" }));
            /** @type {__VLS_StyleScopedClasses['flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
            /** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
            /** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ onClick: (__VLS_ctx.requestTakeover) }, { class: "px-6 py-2.5 bg-amber-500 text-white rounded-xl hover:bg-amber-600 transition-all font-medium text-sm shadow-md active:scale-95" }));
            /** @type {__VLS_StyleScopedClasses['px-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
            /** @type {__VLS_StyleScopedClasses['bg-amber-500']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
            /** @type {__VLS_StyleScopedClasses['hover:bg-amber-600']} */ ;
            /** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
            /** @type {__VLS_StyleScopedClasses['shadow-md']} */ ;
            /** @type {__VLS_StyleScopedClasses['active:scale-95']} */ ;
            (__VLS_ctx.$t('common.takeover_button'));
            __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ onClick: (__VLS_ctx.resumeAgent) }, { class: "px-6 py-2.5 bg-neutral-900 text-white rounded-xl hover:bg-neutral-800 transition-all font-medium text-sm shadow-md active:scale-95" }));
            /** @type {__VLS_StyleScopedClasses['px-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
            /** @type {__VLS_StyleScopedClasses['bg-neutral-900']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
            /** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
            /** @type {__VLS_StyleScopedClasses['hover:bg-neutral-800']} */ ;
            /** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
            /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
            /** @type {__VLS_StyleScopedClasses['shadow-md']} */ ;
            /** @type {__VLS_StyleScopedClasses['active:scale-95']} */ ;
            (__VLS_ctx.$t('common.resume_button'));
        }
        // @ts-ignore
        [$t, $t, $t, $t, $t, $t, $t, requestTakeover, resumeAgent,];
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "sticky bottom-0 pt-4 bg-gradient-to-t from-[#FDFBF7] pb-4 backdrop-blur-sm" }));
    /** @type {__VLS_StyleScopedClasses['sticky']} */ ;
    /** @type {__VLS_StyleScopedClasses['bottom-0']} */ ;
    /** @type {__VLS_StyleScopedClasses['pt-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-gradient-to-t']} */ ;
    /** @type {__VLS_StyleScopedClasses['from-[#FDFBF7]']} */ ;
    /** @type {__VLS_StyleScopedClasses['pb-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['backdrop-blur-sm']} */ ;
    var __VLS_21 = MainInput_vue_1.default;
    // @ts-ignore
    var __VLS_22 = __VLS_asFunctionalComponent1(__VLS_21, new __VLS_21(__assign(__assign({ 'onSubmit': {} }, { minimal: (true) }), { class: "!my-0 !h-auto" })));
    var __VLS_23 = __VLS_22.apply(void 0, __spreadArray([__assign(__assign({ 'onSubmit': {} }, { minimal: (true) }), { class: "!my-0 !h-auto" })], __VLS_functionalComponentArgsRest(__VLS_22), false));
    var __VLS_26 = void 0;
    var __VLS_27 = ({ submit: {} },
        { onSubmit: (__VLS_ctx.handleUserSubmit) });
    /** @type {__VLS_StyleScopedClasses['!my-0']} */ ;
    /** @type {__VLS_StyleScopedClasses['!h-auto']} */ ;
    var __VLS_24;
    var __VLS_25;
}
// @ts-ignore
[handleUserSubmit,];
var __VLS_export = (await Promise.resolve().then(function () { return require('vue'); })).defineComponent({});
exports.default = {};
