# 多样本验证：重新生成 2 个 v 并请求不同页码；外加无 v 负向样本
$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
$base = "https://q.10jqka.com.cn/index/index/board/all/field/zdf/order/desc/page"
for ($i = 1; $i -le 2; $i++) {
    node "$PSScriptRoot\run_sandbox.js" | Out-Null
    $v = (Get-Content "$PSScriptRoot\v_sandbox.txt" -Raw).Trim()
    $page = 4 + $i
    $url = "$base/$page/ajax/1/?probe=v${i}_" + (Get-Random)
    $r = Invoke-WebRequest -Uri $url -Headers @{"User-Agent"=$ua; "Referer"="https://q.10jqka.com.cn/"; "Cookie"="v=$v"} -SkipHttpErrorCheck
    Write-Output ("sample{0} page{1}: status={2} len={3} v={4}" -f $i, $page, $r.StatusCode, $r.Content.Length, $v.Substring(0,16))
    Start-Sleep -Seconds 2
}
$url2 = "$base/7/ajax/1/?probe=neg_" + (Get-Random)
$r2 = Invoke-WebRequest -Uri $url2 -Headers @{"User-Agent"=$ua; "Referer"="https://q.10jqka.com.cn/"} -SkipHttpErrorCheck
Write-Output ("negative(no v): status={0} len={1}" -f $r2.StatusCode, $r2.Content.Length)
