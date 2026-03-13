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
var vue_i18n_1 = require("vue-i18n");
var ChatHistoryPanel_vue_1 = require("./ChatHistoryPanel.vue");
var _a = (0, vue_i18n_1.useI18n)(), locale = _a.locale, t = _a.t;
var emit = defineEmits();
var historyOpen = (0, vue_1.ref)(false);
function toggleHistory() {
    historyOpen.value = !historyOpen.value;
}
function toggleLanguage() {
    locale.value = locale.value === 'zh' ? 'en' : 'zh';
}
function handleNewChat() {
    emit('new-chat');
}
function handleSelectChat(id) {
    emit('select-chat', id);
}
var __VLS_ctx = __assign(__assign(__assign(__assign(__assign({}, {}), {}), {}), {}), {});
var __VLS_components;
var __VLS_intrinsics;
var __VLS_directives;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex h-screen fixed left-0 top-0 z-50" }));
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['h-screen']} */ ;
/** @type {__VLS_StyleScopedClasses['fixed']} */ ;
/** @type {__VLS_StyleScopedClasses['left-0']} */ ;
/** @type {__VLS_StyleScopedClasses['top-0']} */ ;
/** @type {__VLS_StyleScopedClasses['z-50']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.aside, __VLS_intrinsics.aside)(__assign({ class: "w-16 h-full flex flex-col items-center py-6 border-r border-neutral-200/50 bg-white/50 backdrop-blur-sm" }));
/** @type {__VLS_StyleScopedClasses['w-16']} */ ;
/** @type {__VLS_StyleScopedClasses['h-full']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['py-6']} */ ;
/** @type {__VLS_StyleScopedClasses['border-r']} */ ;
/** @type {__VLS_StyleScopedClasses['border-neutral-200/50']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-white/50']} */ ;
/** @type {__VLS_StyleScopedClasses['backdrop-blur-sm']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col gap-6" }));
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-6']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ title: (__VLS_ctx.$t('sidebar.explore')) }, { class: "p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors" }));
/** @type {__VLS_StyleScopedClasses['p-2']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:text-neutral-800']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:bg-neutral-100']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
var __VLS_0;
/** @ts-ignore @type {typeof __VLS_components.Compass} */
lucide_vue_next_1.Compass;
// @ts-ignore
var __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
    size: (20),
    strokeWidth: "2",
}));
var __VLS_2 = __VLS_1.apply(void 0, __spreadArray([{
        size: (20),
        strokeWidth: "2",
    }], __VLS_functionalComponentArgsRest(__VLS_1), false));
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign(__assign(__assign({ onClick: (__VLS_ctx.toggleHistory) }, { title: (__VLS_ctx.$t('sidebar.chat')) }), { class: "p-2 rounded-xl transition-colors" }), { class: (__VLS_ctx.historyOpen ? 'text-neutral-800 bg-neutral-100' : 'text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100') }));
/** @type {__VLS_StyleScopedClasses['p-2']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
var __VLS_5;
/** @ts-ignore @type {typeof __VLS_components.LayoutGrid} */
lucide_vue_next_1.LayoutGrid;
// @ts-ignore
var __VLS_6 = __VLS_asFunctionalComponent1(__VLS_5, new __VLS_5({
    size: (20),
    strokeWidth: "2",
}));
var __VLS_7 = __VLS_6.apply(void 0, __spreadArray([{
        size: (20),
        strokeWidth: "2",
    }], __VLS_functionalComponentArgsRest(__VLS_6), false));
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ title: (__VLS_ctx.$t('sidebar.gallery')) }, { class: "p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors" }));
/** @type {__VLS_StyleScopedClasses['p-2']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:text-neutral-800']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:bg-neutral-100']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
var __VLS_10;
/** @ts-ignore @type {typeof __VLS_components.PlaySquare} */
lucide_vue_next_1.PlaySquare;
// @ts-ignore
var __VLS_11 = __VLS_asFunctionalComponent1(__VLS_10, new __VLS_10({
    size: (20),
    strokeWidth: "2",
}));
var __VLS_12 = __VLS_11.apply(void 0, __spreadArray([{
        size: (20),
        strokeWidth: "2",
    }], __VLS_functionalComponentArgsRest(__VLS_11), false));
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "mt-auto flex flex-col gap-4" }));
/** @type {__VLS_StyleScopedClasses['mt-auto']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-4']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign(__assign({ onClick: (__VLS_ctx.toggleLanguage) }, { class: "p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-all flex flex-col items-center gap-0.5" }), { title: "Switch Language / 切换语言" }));
/** @type {__VLS_StyleScopedClasses['p-2']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:text-neutral-800']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:bg-neutral-100']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-0.5']} */ ;
var __VLS_15;
/** @ts-ignore @type {typeof __VLS_components.Languages} */
lucide_vue_next_1.Languages;
// @ts-ignore
var __VLS_16 = __VLS_asFunctionalComponent1(__VLS_15, new __VLS_15({
    size: (20),
    strokeWidth: "2",
}));
var __VLS_17 = __VLS_16.apply(void 0, __spreadArray([{
        size: (20),
        strokeWidth: "2",
    }], __VLS_functionalComponentArgsRest(__VLS_16), false));
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "text-[9px] font-bold uppercase" }));
/** @type {__VLS_StyleScopedClasses['text-[9px]']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['uppercase']} */ ;
(__VLS_ctx.locale === 'zh' ? 'EN' : 'ZH');
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ title: (__VLS_ctx.$t('sidebar.settings')) }, { class: "p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors" }));
/** @type {__VLS_StyleScopedClasses['p-2']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:text-neutral-800']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:bg-neutral-100']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
var __VLS_20;
/** @ts-ignore @type {typeof __VLS_components.Settings} */
lucide_vue_next_1.Settings;
// @ts-ignore
var __VLS_21 = __VLS_asFunctionalComponent1(__VLS_20, new __VLS_20({
    size: (20),
    strokeWidth: "2",
}));
var __VLS_22 = __VLS_21.apply(void 0, __spreadArray([{
        size: (20),
        strokeWidth: "2",
    }], __VLS_functionalComponentArgsRest(__VLS_21), false));
var __VLS_25;
/** @ts-ignore @type {typeof __VLS_components.Transition | typeof __VLS_components.Transition} */
Transition;
// @ts-ignore
var __VLS_26 = __VLS_asFunctionalComponent1(__VLS_25, new __VLS_25({
    enterActiveClass: "transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
    leaveActiveClass: "transition-all duration-200 ease-in",
    enterFromClass: "opacity-0 -translate-x-4",
    leaveToClass: "opacity-0 -translate-x-4",
}));
var __VLS_27 = __VLS_26.apply(void 0, __spreadArray([{
        enterActiveClass: "transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
        leaveActiveClass: "transition-all duration-200 ease-in",
        enterFromClass: "opacity-0 -translate-x-4",
        leaveToClass: "opacity-0 -translate-x-4",
    }], __VLS_functionalComponentArgsRest(__VLS_26), false));
var __VLS_30 = __VLS_28.slots.default;
if (__VLS_ctx.historyOpen) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-64 h-full border-r border-neutral-200/50 bg-white/90 backdrop-blur-md shadow-md flex flex-col" }));
    /** @type {__VLS_StyleScopedClasses['w-64']} */ ;
    /** @type {__VLS_StyleScopedClasses['h-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['border-r']} */ ;
    /** @type {__VLS_StyleScopedClasses['border-neutral-200/50']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-white/90']} */ ;
    /** @type {__VLS_StyleScopedClasses['backdrop-blur-md']} */ ;
    /** @type {__VLS_StyleScopedClasses['shadow-md']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
    var __VLS_31 = ChatHistoryPanel_vue_1.default;
    // @ts-ignore
    var __VLS_32 = __VLS_asFunctionalComponent1(__VLS_31, new __VLS_31(__assign({ 'onNewChat': {} }, { 'onSelect': {} })));
    var __VLS_33 = __VLS_32.apply(void 0, __spreadArray([__assign({ 'onNewChat': {} }, { 'onSelect': {} })], __VLS_functionalComponentArgsRest(__VLS_32), false));
    var __VLS_36 = void 0;
    var __VLS_37 = ({ newChat: {} },
        { onNewChat: (__VLS_ctx.handleNewChat) });
    var __VLS_38 = ({ select: {} },
        { onSelect: (__VLS_ctx.handleSelectChat) });
    var __VLS_34;
    var __VLS_35;
}
// @ts-ignore
[$t, $t, $t, $t, toggleHistory, historyOpen, historyOpen, toggleLanguage, locale, handleNewChat, handleSelectChat,];
var __VLS_28;
// @ts-ignore
[];
var __VLS_export = (await Promise.resolve().then(function () { return require('vue'); })).defineComponent({
    __typeEmits: {},
});
exports.default = {};
