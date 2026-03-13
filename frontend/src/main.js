"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
var vue_1 = require("vue");
require("./style.css");
var App_vue_1 = require("./App.vue");
var i18n_1 = require("./i18n");
(0, vue_1.createApp)(App_vue_1.default).use(i18n_1.default).mount('#app');
