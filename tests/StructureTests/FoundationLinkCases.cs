// SPDX-License-Identifier: Apache-2.0
using P = ArcForges.Contracts.PublicApi.V1;
using Validation = ArcForges.Contracts.Validation.ContractShapeValidation;

internal static class FoundationLinkCases
{
    public static void Run()
    {
        foreach (var url in new[] { "http://example.test", "https://example.test/a?b=c#d", "http://!", "http://!/?#", "mailto:user@example.test", "mailto:user@example.test?subject=hello" })
            Check(url, true);
        foreach (var url in new[] { "", "http://", "https:///path", "http://?query", "http://#fragment", "mailto:", "HTTPS://example.test", "javascript:alert(1)" })
            Check(url, false);
        foreach (var separator in "\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff")
        {
            Check("http://example.test" + separator, false);
            Check("https://example" + separator + ".test/path", false);
            Check("mailto:user@example.test" + separator, false);
        }
        var authority = "http://" + new string('!', 100000);
        Check(authority, true);
        foreach (var suffix in new[] { "\n", "\u0085", "\ufeff" }) Check(authority + suffix, false);
        Console.WriteLine("Validated focused link schemes, URL parts, shared whitespace and long authority regressions.");
    }

    private static void Check(string url, bool expected)
    {
        if (Validation.IsValid(new P.LinkSpec { Kind = "external", Url = url }) != expected)
            throw new InvalidOperationException("Link validation mismatch.");
    }
}
