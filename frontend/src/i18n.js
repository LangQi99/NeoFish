"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
var vue_i18n_1 = require("vue-i18n");
var zh_json_1 = require("./locales/zh.json");
var en_json_1 = require("./locales/en.json");
var i18n = (0, vue_i18n_1.createI18n)({
    legacy: false,
    locale: 'zh',
    fallbackLocale: 'en',
    messages: {
        zh: zh_json_1.default,
        en: en_json_1.default
    }
});
exports.default = i18n;
