<?php
/**
 * 留言板应用纯函数单元测试（无框架依赖，避免引入 composer/PHPUnit）
 * 运行: php test_guestbook.php   （失败 exit 1，供 CI 质量门使用）
 */
require __DIR__ . '/lib.php';

$failures = 0;

function check(string $name, bool $cond): void {
    global $failures;
    echo $cond ? "  ✅ $name\n" : "  ❌ $name\n";
    if (!$cond) $failures++;
}

echo "clean_input:\n";
check("trim 两侧空格", clean_input("  hello  ") === "hello");
check("空串", clean_input("") === "");
check("null 安全", clean_input(null) === "");

echo "is_valid_message:\n";
check("name+content 合法", is_valid_message("a", "b") === true);
check("name 空则非法", is_valid_message("", "b") === false);
check("content 空则非法", is_valid_message("a", "") === false);

echo "escape:\n";
check("XSS 标签转义", escape("<script>alert(1)</script>") === "&lt;script&gt;alert(1)&lt;/script&gt;");
check("null 安全", escape(null) === "");

echo "render_content:\n";
check("转义 + 换行转 <br />", render_content("<b>a\nb</b>") === "&lt;b&gt;a<br />\nb&lt;/b&gt;");

echo "avatar_initial:\n";
check("取首字符(多字节)", avatar_initial("张三") === "张");
check("空名返回空", avatar_initial("") === "");

if ($failures > 0) {
    echo "\n❌ $failures 个用例失败\n";
    exit(1);
}
echo "\n✅ 全部通过\n";
