# 专业报告的 Alpaca 数据

在自己的交易所账户凭据中保存一个 Alpaca 账户。专业报告直接复用该账户，
无需再配置全局 API Key。凭据及数据缓存按用户和账户隔离。

在 **设置 → 新闻与网页搜索** 中，将搜索提供商选择为 **Alpaca**。
Alpaca 提供指定美股的 Benzinga 新闻；普通网页查询继续使用其他可用搜索源。
在 **专业报告 → 数据源** 中，Alpaca 是已接入的社区数据源，配置状态根据
当前用户保存的账户判断。

新的美股报告会采集股票价格、报价、成交及历史 K 线、个股新闻、近期合约的
期权快照及可用的隐含波动率和 Greeks、公司行动，以及证券公开属性。
会计基本面仍由原有财报和 SEC 数据源负责。已有报告需要重新生成才能采集新增数据。

使用以下配置（报告数据源默认值见 `.env.example`，搜索提供商需主动选择）：

```dotenv
ALPACA_REPORT_ENABLED=true
ALPACA_REPORT_FEED=iex
ALPACA_OPTIONS_FEED=indicative
SEARCH_PROVIDER=alpaca
```

IEX 仅覆盖单一交易场所。indicative 期权报价不是 OPRA 综合报价，报告证据保留
这些限制。期权采集限于近期合约，并标明样本范围。快照不提供持仓量和成交量比率，
不会虚构这些指标。SIP 和 OPRA 需要账户拥有对应权限。

这些 Alpaca 请求均为只读。可用性取决于账户凭据、数据权限、限流和网络。
可选数据获取失败时保留为空，并记录采集状态；价格、K 线和新闻可以使用已有备用源，
保留实际来源。缺失的会计指标不会用零填充。

官方说明：[市场数据](https://docs.alpaca.markets/docs/about-market-data-api)、
[新闻](https://docs.alpaca.markets/us/reference/news-3)、
[期权链](https://docs.alpaca.markets/us/reference/optionchain)。
