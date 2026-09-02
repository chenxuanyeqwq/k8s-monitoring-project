<?php
/**
 * 留言板应用纯函数库（2026-09-02 CI/CD 优化抽出）
 * 职责：可被单测的纯函数，不依赖 $_POST / DB / 输出。
 * 使用：index.php require 本文件后调用。
 */

/** 清洗输入：trim；null 安全（空提交返回空串） */
function clean_input($value): string {
    if ($value === null) return '';
    return trim($value);
}

/** 留言是否有效：name 和 content 都非空 */
function is_valid_message(string $name, string $content): bool {
    return $name !== '' && $content !== '';
}

/** HTML 转义（XSS 防护）；null 安全 */
function escape($value): string {
    if ($value === null) return '';
    return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

/** 渲染内容：转义 + 换行转 <br /> */
function render_content($content): string {
    return nl2br(escape($content));
}

/** 头像首字符（优先 mb_substr 支持多字节） */
function avatar_initial(string $name): string {
    if ($name === '') return '';
    return function_exists('mb_substr') ? mb_substr($name, 0, 1, 'UTF-8') : substr($name, 0, 1);
}
