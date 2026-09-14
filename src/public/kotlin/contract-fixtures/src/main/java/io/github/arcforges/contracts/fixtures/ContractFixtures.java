// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.contracts.fixtures;

import java.io.InputStream;

/** Shared cross-language wire fixtures. Intended for consumer tests, not application runtime. */
public final class ContractFixtures {
    private ContractFixtures() {}

    /**
     * Opens the UTF-8 Hello success/error cases; the caller closes the stream.
     * @return fixture stream
     * @throws IllegalStateException if the published resource is missing
     */
    public static InputStream openHello() {
        InputStream stream = ContractFixtures.class.getResourceAsStream("/arcforges/fixtures/hello.json");
        if (stream == null) throw new IllegalStateException("Hello contract fixture is missing");
        return stream;
    }
}
