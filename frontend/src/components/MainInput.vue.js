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
var props = defineProps();
var query = (0, vue_1.ref)('');
var pendingImages = (0, vue_1.ref)([]); // base64 data-URLs
var fileInputRef = (0, vue_1.ref)(null);
var emit = defineEmits();
// ── File picker ──────────────────────────────────────────────────────────────
function openFilePicker() {
    var _a;
    (_a = fileInputRef.value) === null || _a === void 0 ? void 0 : _a.click();
}
function onFilesSelected(e) {
    var files = e.target.files;
    if (!files)
        return;
    Array.from(files).forEach(readImageFile);
    e.target.value = '';
}
function readImageFile(file) {
    if (!file.type.startsWith('image/'))
        return;
    var reader = new FileReader();
    reader.onload = function () {
        if (typeof reader.result === 'string') {
            pendingImages.value.push(reader.result);
        }
    };
    reader.readAsDataURL(file);
}
// ── Clipboard paste ──────────────────────────────────────────────────────────
function onPaste(e) {
    var _a;
    var items = (_a = e.clipboardData) === null || _a === void 0 ? void 0 : _a.items;
    if (!items)
        return;
    for (var _i = 0, _b = Array.from(items); _i < _b.length; _i++) {
        var item = _b[_i];
        if (item.type.startsWith('image/')) {
            var file = item.getAsFile();
            if (file)
                readImageFile(file);
        }
    }
}
function removeImage(idx) {
    pendingImages.value.splice(idx, 1);
}
// ── Submit ───────────────────────────────────────────────────────────────────
function handleSubmit(e) {
    if (e instanceof KeyboardEvent && e.isComposing)
        return;
    var hasText = query.value.trim().length > 0;
    var hasImages = pendingImages.value.length > 0;
    if (!hasText && !hasImages)
        return;
    emit('submit', {
        text: query.value.trim(),
        images: __spreadArray([], pendingImages.value, true),
    });
    query.value = '';
    pendingImages.value = [];
}
var __VLS_ctx = __assign(__assign(__assign(__assign(__assign({}, {}), {}), {}), {}), {});
var __VLS_components;
var __VLS_intrinsics;
var __VLS_directives;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex flex-col items-center justify-center w-full max-w-3xl mx-auto px-4" }, { class: ({ 'h-full': !__VLS_ctx.minimal }) }));
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['max-w-3xl']} */ ;
/** @type {__VLS_StyleScopedClasses['mx-auto']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['h-full']} */ ;
if (!__VLS_ctx.minimal) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)(__assign({ class: "font-serif text-4xl md:text-5xl lg:text-6xl text-neutral-800 mb-12 tracking-wide font-medium" }));
    /** @type {__VLS_StyleScopedClasses['font-serif']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-4xl']} */ ;
    /** @type {__VLS_StyleScopedClasses['md:text-5xl']} */ ;
    /** @type {__VLS_StyleScopedClasses['lg:text-6xl']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-neutral-800']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-12']} */ ;
    /** @type {__VLS_StyleScopedClasses['tracking-wide']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
    (__VLS_ctx.$t('landing.hero_title'));
}
if (__VLS_ctx.pendingImages.length > 0) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "w-full max-w-2xl mb-2 flex flex-wrap gap-2 px-2" }));
    /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['max-w-2xl']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
    var _loop_1 = function (src, idx) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ key: (idx) }, { class: "relative group w-16 h-16 rounded-xl overflow-hidden border border-neutral-200 shadow-sm flex-shrink-0" }));
        /** @type {__VLS_StyleScopedClasses['relative']} */ ;
        /** @type {__VLS_StyleScopedClasses['group']} */ ;
        /** @type {__VLS_StyleScopedClasses['w-16']} */ ;
        /** @type {__VLS_StyleScopedClasses['h-16']} */ ;
        /** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
        /** @type {__VLS_StyleScopedClasses['overflow-hidden']} */ ;
        /** @type {__VLS_StyleScopedClasses['border']} */ ;
        /** @type {__VLS_StyleScopedClasses['border-neutral-200']} */ ;
        /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.img)(__assign(__assign({ src: (src) }, { class: "w-full h-full object-cover" }), { alt: "attached image" }));
        /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
        /** @type {__VLS_StyleScopedClasses['h-full']} */ ;
        /** @type {__VLS_StyleScopedClasses['object-cover']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ onClick: function () {
                var _a = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    _a[_i] = arguments[_i];
                }
                var $event = _a[0];
                if (!(__VLS_ctx.pendingImages.length > 0))
                    return;
                __VLS_ctx.removeImage(idx);
                // @ts-ignore
                [minimal, minimal, $t, pendingImages, pendingImages, removeImage,];
            } }, { class: "absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center" }));
        /** @type {__VLS_StyleScopedClasses['absolute']} */ ;
        /** @type {__VLS_StyleScopedClasses['inset-0']} */ ;
        /** @type {__VLS_StyleScopedClasses['bg-black/40']} */ ;
        /** @type {__VLS_StyleScopedClasses['opacity-0']} */ ;
        /** @type {__VLS_StyleScopedClasses['group-hover:opacity-100']} */ ;
        /** @type {__VLS_StyleScopedClasses['transition-opacity']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
        var __VLS_0 = void 0;
        /** @ts-ignore @type {typeof __VLS_components.X} */
        lucide_vue_next_1.X;
        // @ts-ignore
        var __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0(__assign({ size: (16) }, { class: "text-white" })));
        var __VLS_2 = __VLS_1.apply(void 0, __spreadArray([__assign({ size: (16) }, { class: "text-white" })], __VLS_functionalComponentArgsRest(__VLS_1), false));
        /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
        // @ts-ignore
        [];
    };
    for (var _i = 0, _a = __VLS_vFor((__VLS_ctx.pendingImages)); _i < _a.length; _i++) {
        var _b = _a[_i], src = _b[0], idx = _b[1];
        _loop_1(src, idx);
    }
}
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "relative w-full max-w-2xl bg-white rounded-3xl shadow-soft p-2 flex items-center transition-all duration-300 focus-within:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.1)] border border-neutral-100" }, { class: (__VLS_ctx.pendingImages.length > 0 ? 'rounded-t-xl' : '') }));
/** @type {__VLS_StyleScopedClasses['relative']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['max-w-2xl']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-white']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-3xl']} */ ;
/** @type {__VLS_StyleScopedClasses['shadow-soft']} */ ;
/** @type {__VLS_StyleScopedClasses['p-2']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
/** @type {__VLS_StyleScopedClasses['duration-300']} */ ;
/** @type {__VLS_StyleScopedClasses['focus-within:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.1)]']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-neutral-100']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.input)(__assign(__assign({ onChange: (__VLS_ctx.onFilesSelected) }, { ref: "fileInputRef", type: "file", accept: "image/*", multiple: true }), { class: "hidden" }));
/** @type {__VLS_StyleScopedClasses['hidden']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign(__assign(__assign({ onClick: (__VLS_ctx.openFilePicker) }, { title: (__VLS_ctx.$t('input.attach_image')) }), { class: "p-3 text-neutral-400 hover:text-neutral-700 transition-colors rounded-full hover:bg-neutral-50 ml-1 relative" }), { class: (__VLS_ctx.pendingImages.length > 0 ? 'text-blue-500' : '') }));
/** @type {__VLS_StyleScopedClasses['p-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-neutral-400']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:text-neutral-700']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:bg-neutral-50']} */ ;
/** @type {__VLS_StyleScopedClasses['ml-1']} */ ;
/** @type {__VLS_StyleScopedClasses['relative']} */ ;
var __VLS_5;
/** @ts-ignore @type {typeof __VLS_components.Plus} */
lucide_vue_next_1.Plus;
// @ts-ignore
var __VLS_6 = __VLS_asFunctionalComponent1(__VLS_5, new __VLS_5({
    size: (22),
    strokeWidth: "2",
}));
var __VLS_7 = __VLS_6.apply(void 0, __spreadArray([{
        size: (22),
        strokeWidth: "2",
    }], __VLS_functionalComponentArgsRest(__VLS_6), false));
if (__VLS_ctx.pendingImages.length > 0) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)(__assign({ class: "absolute -top-0.5 -right-0.5 w-4 h-4 bg-blue-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center" }));
    /** @type {__VLS_StyleScopedClasses['absolute']} */ ;
    /** @type {__VLS_StyleScopedClasses['-top-0.5']} */ ;
    /** @type {__VLS_StyleScopedClasses['-right-0.5']} */ ;
    /** @type {__VLS_StyleScopedClasses['w-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['h-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-blue-500']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-[9px]']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
    /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
    (__VLS_ctx.pendingImages.length);
}
__VLS_asFunctionalElement1(__VLS_intrinsics.input)(__assign(__assign(__assign(__assign({ onKeydown: (__VLS_ctx.handleSubmit) }, { onPaste: (__VLS_ctx.onPaste) }), { value: (__VLS_ctx.query), type: "text" }), { class: "flex-1 bg-transparent border-none outline-none px-4 py-3 text-lg text-neutral-800 placeholder:text-neutral-400 font-sans" }), { placeholder: (__VLS_ctx.$t('landing.input_placeholder')) }));
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-transparent']} */ ;
/** @type {__VLS_StyleScopedClasses['border-none']} */ ;
/** @type {__VLS_StyleScopedClasses['outline-none']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['text-neutral-800']} */ ;
/** @type {__VLS_StyleScopedClasses['placeholder:text-neutral-400']} */ ;
/** @type {__VLS_StyleScopedClasses['font-sans']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign(__assign({ onClick: (__VLS_ctx.handleSubmit) }, { class: "p-3 rounded-2xl transition-colors min-w-[48px] flex items-center justify-center mr-1" }), { class: ((__VLS_ctx.query.trim() || __VLS_ctx.pendingImages.length > 0) ? 'bg-black text-white hover:bg-neutral-800' : 'bg-neutral-100 text-neutral-400') }));
/** @type {__VLS_StyleScopedClasses['p-3']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-2xl']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['min-w-[48px]']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
/** @type {__VLS_StyleScopedClasses['mr-1']} */ ;
var __VLS_10;
/** @ts-ignore @type {typeof __VLS_components.ArrowUp} */
lucide_vue_next_1.ArrowUp;
// @ts-ignore
var __VLS_11 = __VLS_asFunctionalComponent1(__VLS_10, new __VLS_10({
    size: (20),
    strokeWidth: "3",
}));
var __VLS_12 = __VLS_11.apply(void 0, __spreadArray([{
        size: (20),
        strokeWidth: "3",
    }], __VLS_functionalComponentArgsRest(__VLS_11), false));
if (!__VLS_ctx.minimal) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)(__assign({ class: "flex gap-4 mt-8 w-full max-w-2xl px-2" }));
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['gap-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['mt-8']} */ ;
    /** @type {__VLS_StyleScopedClasses['w-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['max-w-2xl']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ class: "flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/60 hover:bg-white border border-neutral-200/50 text-neutral-600 text-sm font-medium transition-all shadow-sm" }));
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
    /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-white/60']} */ ;
    /** @type {__VLS_StyleScopedClasses['hover:bg-white']} */ ;
    /** @type {__VLS_StyleScopedClasses['border']} */ ;
    /** @type {__VLS_StyleScopedClasses['border-neutral-200/50']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-neutral-600']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
    /** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
    /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
    var __VLS_15 = void 0;
    /** @ts-ignore @type {typeof __VLS_components.FileText} */
    lucide_vue_next_1.FileText;
    // @ts-ignore
    var __VLS_16 = __VLS_asFunctionalComponent1(__VLS_15, new __VLS_15(__assign({ size: (16) }, { class: "text-orange-400" })));
    var __VLS_17 = __VLS_16.apply(void 0, __spreadArray([__assign({ size: (16) }, { class: "text-orange-400" })], __VLS_functionalComponentArgsRest(__VLS_16), false));
    /** @type {__VLS_StyleScopedClasses['text-orange-400']} */ ;
    (__VLS_ctx.$t('landing.suggest_ppt'));
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)(__assign({ class: "flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/60 hover:bg-white border border-neutral-200/50 text-neutral-600 text-sm font-medium transition-all shadow-sm" }));
    /** @type {__VLS_StyleScopedClasses['flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['items-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
    /** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
    /** @type {__VLS_StyleScopedClasses['bg-white/60']} */ ;
    /** @type {__VLS_StyleScopedClasses['hover:bg-white']} */ ;
    /** @type {__VLS_StyleScopedClasses['border']} */ ;
    /** @type {__VLS_StyleScopedClasses['border-neutral-200/50']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-neutral-600']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-medium']} */ ;
    /** @type {__VLS_StyleScopedClasses['transition-all']} */ ;
    /** @type {__VLS_StyleScopedClasses['shadow-sm']} */ ;
    var __VLS_20 = void 0;
    /** @ts-ignore @type {typeof __VLS_components.Globe} */
    lucide_vue_next_1.Globe;
    // @ts-ignore
    var __VLS_21 = __VLS_asFunctionalComponent1(__VLS_20, new __VLS_20(__assign({ size: (16) }, { class: "text-blue-400" })));
    var __VLS_22 = __VLS_21.apply(void 0, __spreadArray([__assign({ size: (16) }, { class: "text-blue-400" })], __VLS_functionalComponentArgsRest(__VLS_21), false));
    /** @type {__VLS_StyleScopedClasses['text-blue-400']} */ ;
    (__VLS_ctx.$t('landing.suggest_analyze'));
}
// @ts-ignore
[minimal, $t, $t, $t, $t, pendingImages, pendingImages, pendingImages, pendingImages, pendingImages, onFilesSelected, openFilePicker, handleSubmit, handleSubmit, onPaste, query, query,];
var __VLS_export = (await Promise.resolve().then(function () { return require('vue'); })).defineComponent({
    __typeEmits: {},
    __typeProps: {},
});
exports.default = {};
