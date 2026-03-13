"use strict";
/// <reference types="../../../../../../.npm/_npx/2db181330ea4b15b/node_modules/@vue/language-core/types/template-helpers.d.ts" />
/// <reference types="../../../../../../.npm/_npx/2db181330ea4b15b/node_modules/@vue/language-core/types/props-fallback.d.ts" />
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
var lucide_vue_next_1 = require("lucide-vue-next");
var useChatHistory_1 = require("../composables/useChatHistory");
var vue_i18n_1 = require("vue-i18n");
var t = (0, vue_i18n_1.useI18n)().t;
var _a = (0, useChatHistory_1.useChatHistory)(), sessions = _a.sessions, activeChatId = _a.activeChatId, createNewChat = _a.createNewChat, deleteChat = _a.deleteChat, renameChat = _a.renameChat;
var emit = defineEmits();
// Inline rename state
var editingId = (0, vue_1.ref)(null);
var editingTitle = (0, vue_1.ref)('');
function startRename(session) {
    editingId.value = session.id;
    editingTitle.value = session.title;
}
function confirmRename(id) {
    return __awaiter(this, void 0, void 0, function () {
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    if (!editingTitle.value.trim()) return [3 /*break*/, 2];
                    return [4 /*yield*/, renameChat(id, editingTitle.value.trim())];
                case 1:
                    _a.sent();
                    _a.label = 2;
                case 2:
                    editingId.value = null;
                    return [2 /*return*/];
            }
        });
    });
}
function cancelRename() {
    editingId.value = null;
}
function handleDelete(id) {
    return __awaiter(this, void 0, void 0, function () {
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0: return [4 /*yield*/, deleteChat(id)
                    // If we deleted the active one, parent handles switching via activeChatId change
                ];
                case 1:
                    _a.sent();
                    return [2 /*return*/];
            }
        });
    });
}
function handleNewChat() {
    return __awaiter(this, void 0, void 0, function () {
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0: return [4 /*yield*/, createNewChat()];
                case 1:
                    _a.sent();
                    emit('new-chat');
                    return [2 /*return*/];
            }
        });
    });
}
function handleSelect(id) {
    activeChatId.value = id;
    emit('select', id);
}
function formatDate(iso) {
    var d = new Date(iso);
    var now = new Date();
    var diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
    if (diffDays === 0)
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 1)
        return t('history.yesterday');
    if (diffDays < 7)
        return t('history.days_ago', { n: diffDays });
    return d.toLocaleDateString();
}
var __VLS_ctx = __assign(__assign(__assign(__assign(__assign({}, {}), {}), {}), {}), {});
var __VLS_components;
var __VLS_intrinsics;
var __VLS_directives;
/** @type {__VLS_StyleScopedClasses['custom-scrollbar']} */ ;
/** @type {__VLS_StyleScopedClasses['custom-scrollbar']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col h-full" }));
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['h-full']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "px-3 py-4 border-b border-neutral-100" }));
/** @type {__VLS_StyleScopedClasses['px-3']} */ ;
/** @type {__VLS_StyleScopedClasses['py-4']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-neutral-100']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)(__assign({ class: "text-xs font-semibold text-neutral-500 uppercase tracking-widest mb-3" }));
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-neutral-500']} */ ;
/** @type {__VLS_StyleScopedClasses['uppercase']} */ ;
/** @type {__VLS_StyleScopedClasses['tracking-widest']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
(__VLS_ctx.$t('history.panel_title'));
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ onClick: (__VLS_ctx.handleNewChat) }, { class: "w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-neutral-900 text-white text-sm font-medium hover:bg-neutral-700 transition-all active:scale-95" }));
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['px-3']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-neutral-900']} */ ;
/** @type {__VLS_StyleScopedClasses['text-white']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:bg-neutral-700']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
/** @type {__VLS_StyleScopedClasses['active:scale-95']} */ ;
var __VLS_0;
/** @ts-ignore @type {typeof __VLS_components.Plus} */
lucide_vue_next_1.Plus;
// @ts-ignore
var __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
    size: (16),
}));
var __VLS_2 = __VLS_1.apply(void 0, __spreadArray([{
        size: (16),
    }], __VLS_functionalComponentArgsRest(__VLS_1), false));
(__VLS_ctx.$t('history.new_chat'));
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex-1 overflow-y-auto py-2 custom-scrollbar" }));
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['overflow-y-auto']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2']} */ ;
/** @type {__VLS_StyleScopedClasses['custom-scrollbar']} */ ;
if (__VLS_ctx.sessions.length === 0) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col items-center justify-center h-40 text-neutral-400 gap-2" }));
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
    /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['h-40']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
    /** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
    var __VLS_5 = void 0;
    /** @ts-ignore @type {typeof __VLS_components.MessageSquare} */
    lucide_vue_next_1.MessageSquare;
    // @ts-ignore
    var __VLS_6 = __VLS_asFunctionalComponent1(__VLS_5, new __VLS_5({
        size: (28),
        strokeWidth: "1.5",
    }));
    var __VLS_7 = __VLS_6.apply(void 0, __spreadArray([{
            size: (28),
            strokeWidth: "1.5",
        }], __VLS_functionalComponentArgsRest(__VLS_6), false));
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)(__assign({ class: "text-xs" }));
    /** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
    (__VLS_ctx.$t('history.empty_state'));
}
var _loop_1 = function (session) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign(__assign(__assign({ onClick: function () {
            var _a = [];
            for (var _i = 0; _i < arguments.length; _i++) {
                _a[_i] = arguments[_i];
            }
            var $event = _a[0];
            __VLS_ctx.handleSelect(session.id);
            // @ts-ignore
            [$t, $t, $t, handleNewChat, sessions, sessions, handleSelect,];
        } }, { key: (session.id) }), { class: "group mx-2 mb-1 rounded-xl transition-all cursor-pointer" }), { class: (session.id === __VLS_ctx.activeChatId
            ? 'bg-neutral-100'
            : 'hover:bg-neutral-50') }));
    /** @type {__VLS_StyleScopedClasses['group']} */ ;
    /** @type {__VLS_StyleScopedClasses['mx-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
    /** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
    /** @type {__VLS_StyleScopedClasses['cursor-pointer']} */ ;
    if (__VLS_ctx.editingId === session.id) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ onClick: function () { } }, { class: "flex items-center gap-1 p-2" }));
        /** @type {__VLS_StyleScopedClasses['flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['gap-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['p-2']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.input)(__assign(__assign(__assign({ onKeydown: function () {
                var _a = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    _a[_i] = arguments[_i];
                }
                var $event = _a[0];
                if (!(__VLS_ctx.editingId === session.id))
                    return;
                __VLS_ctx.confirmRename(session.id);
                // @ts-ignore
                [activeChatId, editingId, confirmRename,];
            } }, { onKeydown: (__VLS_ctx.cancelRename) }), { class: "flex-1 text-sm text-neutral-800 bg-white border border-neutral-300 rounded-lg px-2 py-1 outline-none focus:border-neutral-500" }), { placeholder: (__VLS_ctx.$t('history.rename_placeholder')), autofocus: true }));
        (__VLS_ctx.editingTitle);
        /** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-neutral-800']} */ ;
        /** @type {__VLS_StyleScopedClasses['bg-white']} */ ;
        /** @type {__VLS_StyleScopedClasses['border']} */ ;
        /** @type {__VLS_StyleScopedClasses['border-neutral-300']} */ ;
        /** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
        /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['py-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['outline-none']} */ ;
        /** @type {__VLS_StyleScopedClasses['focus:border-neutral-500']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ onClick: function () {
                var _a = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    _a[_i] = arguments[_i];
                }
                var $event = _a[0];
                if (!(__VLS_ctx.editingId === session.id))
                    return;
                __VLS_ctx.confirmRename(session.id);
                // @ts-ignore
                [$t, confirmRename, cancelRename, editingTitle,];
            } }, { class: "p-1 text-green-600 hover:bg-green-50 rounded-md transition-colors" }));
        /** @type {__VLS_StyleScopedClasses['p-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-green-600']} */ ;
        /** @type {__VLS_StyleScopedClasses['hover:bg-green-50']} */ ;
        /** @type {__VLS_StyleScopedClasses['rounded-md']} */ ;
        /** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
        var __VLS_10 = void 0;
        /** @ts-ignore @type {typeof __VLS_components.Check} */
        lucide_vue_next_1.Check;
        // @ts-ignore
        var __VLS_11 = __VLS_asFunctionalComponent1(__VLS_10, new __VLS_10({
            size: (14),
        }));
        var __VLS_12 = __VLS_11.apply(void 0, __spreadArray([{
                size: (14),
            }], __VLS_functionalComponentArgsRest(__VLS_11), false));
        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ onClick: (__VLS_ctx.cancelRename) }, { class: "p-1 text-neutral-400 hover:bg-neutral-100 rounded-md transition-colors" }));
        /** @type {__VLS_StyleScopedClasses['p-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
        /** @type {__VLS_StyleScopedClasses['hover:bg-neutral-100']} */ ;
        /** @type {__VLS_StyleScopedClasses['rounded-md']} */ ;
        /** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
        var __VLS_15 = void 0;
        /** @ts-ignore @type {typeof __VLS_components.X} */
        lucide_vue_next_1.X;
        // @ts-ignore
        var __VLS_16 = __VLS_asFunctionalComponent1(__VLS_15, new __VLS_15({
            size: (14),
        }));
        var __VLS_17 = __VLS_16.apply(void 0, __spreadArray([{
                size: (14),
            }], __VLS_functionalComponentArgsRest(__VLS_16), false));
    }
    else {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex items-start gap-2 p-2.5 pr-2" }));
        /** @type {__VLS_StyleScopedClasses['flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['items-start']} */ ;
        /** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['p-2.5']} */ ;
        /** @type {__VLS_StyleScopedClasses['pr-2']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex-1 min-w-0" }));
        /** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['min-w-0']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)(__assign({ class: "text-sm font-medium text-neutral-800 truncate leading-snug" }));
        /** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
        /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-neutral-800']} */ ;
        /** @type {__VLS_StyleScopedClasses['truncate']} */ ;
        /** @type {__VLS_StyleScopedClasses['leading-snug']} */ ;
        (session.title || __VLS_ctx.$t('history.new_chat'));
        if (session.preview) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)(__assign({ class: "text-xs text-neutral-400 truncate mt-0.5 leading-relaxed" }));
            /** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
            /** @type {__VLS_StyleScopedClasses['truncate']} */ ;
            /** @type {__VLS_StyleScopedClasses['mt-0.5']} */ ;
            /** @type {__VLS_StyleScopedClasses['leading-relaxed']} */ ;
            (session.preview);
        }
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)(__assign({ class: "text-[10px] text-neutral-300 mt-1" }));
        /** @type {__VLS_StyleScopedClasses['text-[10px]']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-neutral-300']} */ ;
        /** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
        (__VLS_ctx.formatDate(session.created_at));
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ onClick: function () { } }, { class: "flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 mt-0.5" }));
        /** @type {__VLS_StyleScopedClasses['flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['gap-0.5']} */ ;
        /** @type {__VLS_StyleScopedClasses['opacity-0']} */ ;
        /** @type {__VLS_StyleScopedClasses['group-hover:opacity-100']} */ ;
        /** @type {__VLS_StyleScopedClasses['transition-opacity']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
        /** @type {__VLS_StyleScopedClasses['mt-0.5']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign(__assign({ onClick: function () {
                var _a = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    _a[_i] = arguments[_i];
                }
                var $event = _a[0];
                if (!!(__VLS_ctx.editingId === session.id))
                    return;
                __VLS_ctx.startRename(session);
                // @ts-ignore
                [$t, cancelRename, formatDate, startRename,];
            } }, { class: "p-1 text-neutral-400 hover:text-neutral-700 hover:bg-neutral-200 rounded-md transition-colors" }), { title: (__VLS_ctx.$t('history.rename')) }));
        /** @type {__VLS_StyleScopedClasses['p-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
        /** @type {__VLS_StyleScopedClasses['hover:text-neutral-700']} */ ;
        /** @type {__VLS_StyleScopedClasses['hover:bg-neutral-200']} */ ;
        /** @type {__VLS_StyleScopedClasses['rounded-md']} */ ;
        /** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
        var __VLS_20 = void 0;
        /** @ts-ignore @type {typeof __VLS_components.Pencil} */
        lucide_vue_next_1.Pencil;
        // @ts-ignore
        var __VLS_21 = __VLS_asFunctionalComponent1(__VLS_20, new __VLS_20({
            size: (12),
        }));
        var __VLS_22 = __VLS_21.apply(void 0, __spreadArray([{
                size: (12),
            }], __VLS_functionalComponentArgsRest(__VLS_21), false));
        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign(__assign({ onClick: function () {
                var _a = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    _a[_i] = arguments[_i];
                }
                var $event = _a[0];
                if (!!(__VLS_ctx.editingId === session.id))
                    return;
                __VLS_ctx.handleDelete(session.id);
                // @ts-ignore
                [$t, handleDelete,];
            } }, { class: "p-1 text-neutral-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors" }), { title: (__VLS_ctx.$t('history.delete')) }));
        /** @type {__VLS_StyleScopedClasses['p-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
        /** @type {__VLS_StyleScopedClasses['hover:text-red-500']} */ ;
        /** @type {__VLS_StyleScopedClasses['hover:bg-red-50']} */ ;
        /** @type {__VLS_StyleScopedClasses['rounded-md']} */ ;
        /** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
        var __VLS_25 = void 0;
        /** @ts-ignore @type {typeof __VLS_components.Trash2} */
        lucide_vue_next_1.Trash2;
        // @ts-ignore
        var __VLS_26 = __VLS_asFunctionalComponent1(__VLS_25, new __VLS_25({
            size: (12),
        }));
        var __VLS_27 = __VLS_26.apply(void 0, __spreadArray([{
                size: (12),
            }], __VLS_functionalComponentArgsRest(__VLS_26), false));
    }
    // @ts-ignore
    [$t,];
};
for (var _i = 0, _b = __VLS_vFor((__VLS_ctx.sessions)); _i < _b.length; _i++) {
    var session = _b[_i][0];
    _loop_1(session);
}
// @ts-ignore
[];
var __VLS_export = (await Promise.resolve().then(function () { return require('vue'); })).defineComponent({
    __typeEmits: {},
});
exports.default = {};
